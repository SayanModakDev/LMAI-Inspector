"""
Universal Label-Value Association Engine.

Associates statutory declaration labels with nearby candidate values based on:
- Same-line lexical containment
- Next-line / multi-line vertical continuity
- Geometric / 2D bounding-box spatial proximity (RIGHT, BELOW)
- Semantic section compatibility and negative section penalties
"""

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple, Union

from app.extraction.evidence_model import (
    AnchorRelation,
    EvidenceCandidate,
    SourceType,
    ValidationState,
)


@dataclass
class AssociatedCandidate:
    """Represents a discovered label-value pairing."""
    label_text: str
    value_text: str
    relation: str  # AnchorRelation value
    line_index: int
    value_line_index: int
    distance: float
    confidence: float
    raw_span: str
    bounding_box: Optional[Dict[str, Any]] = None
    semantic_section: str = "UNKNOWN"

    def to_evidence_candidate(
        self,
        candidate_field: str,
        source_image: str = "",
        relevance_score: float = 0.9,
    ) -> EvidenceCandidate:
        """Promote to canonical EvidenceCandidate."""
        return EvidenceCandidate(
            raw_text=self.raw_span,
            normalized_text=self.value_text,
            source_image=source_image,
            source_type=SourceType.OCR.value,
            ocr_confidence=self.confidence,
            bounding_box=self.bounding_box,
            line_id=self.value_line_index,
            semantic_section=self.semantic_section,
            anchor_label=self.label_text,
            anchor_relation=self.relation,
            candidate_field=candidate_field,
            relevance_score=relevance_score,
            validation_state=ValidationState.UNASSESSED.value,
            metadata={"distance": self.distance, "label_line": self.line_index},
        )


class LabelValueAssociator:
    """
    Universal associator that finds semantically and spatially valid
    values corresponding to declaration labels.
    """

    @staticmethod
    def _compute_bbox_distance(box1: Dict[str, Any], box2: Dict[str, Any]) -> Tuple[float, str]:
        """
        Compute geometric center distance and relative relation between two bounding boxes.
        Boxes can be {'x': ..., 'y': ..., 'w': ..., 'h': ...} or [x1, y1, x2, y2].
        """
        def parse_box(b: Union[Dict, List, Tuple]):
            if isinstance(b, dict):
                x = b.get('x', b.get('left', 0))
                y = b.get('y', b.get('top', 0))
                w = b.get('w', b.get('width', 0))
                h = b.get('h', b.get('height', 0))
                return x, y, x + w, y + h, x + w / 2, y + h / 2
            elif isinstance(b, (list, tuple)) and len(b) >= 4:
                return b[0], b[1], b[2], b[3], (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            return 0, 0, 0, 0, 0, 0

        x1_min, y1_min, x1_max, y1_max, cx1, cy1 = parse_box(box1)
        x2_min, y2_min, x2_max, y2_max, cx2, cy2 = parse_box(box2)

        dist = math.hypot(cx2 - cx1, cy2 - cy1)

        # Determine geometric relation
        dx = cx2 - cx1
        dy = cy2 - cy1

        # Check same horizontal row (right or left)
        overlap_y = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
        h_min = min(y1_max - y1_min, y2_max - y2_min) if (y1_max > y1_min and y2_max > y2_min) else 1
        is_same_row = (overlap_y / h_min) > 0.4 if h_min > 0 else abs(dy) < 20

        if is_same_row:
            relation = AnchorRelation.RIGHT.value if dx >= 0 else AnchorRelation.LEFT.value
        elif dy > 0:
            relation = AnchorRelation.BELOW.value
        else:
            relation = AnchorRelation.ABOVE.value

        return dist, relation

    @classmethod
    def find_associations(
        cls,
        lines: List[str],
        label_pattern: Union[str, Pattern],
        value_pattern: Union[str, Pattern],
        ocr_items: Optional[List[Dict[str, Any]]] = None,
        section_map: Optional[Dict[int, str]] = None,
        value_filter: Optional[Callable[[str], bool]] = None,
        max_line_lookahead: int = 2,
    ) -> List[AssociatedCandidate]:
        """
        Find candidate values associated with an anchor label across text lines and spatial OCR items.
        """
        label_re = re.compile(label_pattern, re.IGNORECASE) if isinstance(label_pattern, str) else label_pattern
        val_re = re.compile(value_pattern, re.IGNORECASE) if isinstance(value_pattern, str) else value_pattern

        candidates: List[AssociatedCandidate] = []

        for idx, line in enumerate(lines):
            line_clean = line.strip()
            if not line_clean:
                continue

            sec = (section_map or {}).get(idx, "UNKNOWN")
            m_label = label_re.search(line_clean)
            if not m_label:
                continue

            anchor_label_text = m_label.group(0).strip()
            after_label_text = line_clean[m_label.end():].strip(' :;,-')

            # 1. SAME LINE check
            if after_label_text:
                m_val = val_re.search(after_label_text)
                if m_val:
                    raw_val = m_val.group(1) if m_val.groups() else m_val.group(0)
                    raw_val = raw_val.strip()
                    if not value_filter or value_filter(raw_val):
                        candidates.append(AssociatedCandidate(
                            label_text=anchor_label_text,
                            value_text=raw_val,
                            relation=AnchorRelation.SAME_LINE.value,
                            line_index=idx,
                            value_line_index=idx,
                            distance=0.0,
                            confidence=0.90,
                            raw_span=line_clean,
                            semantic_section=sec,
                        ))
                        continue

            # 2. BELOW (Next lines) check
            for offset in range(1, max_line_lookahead + 1):
                next_idx = idx + offset
                if next_idx >= len(lines):
                    break
                next_line = lines[next_idx].strip()
                if not next_line:
                    continue

                m_val_next = val_re.search(next_line)
                if m_val_next:
                    raw_val = m_val_next.group(1) if m_val_next.groups() else m_val_next.group(0)
                    raw_val = raw_val.strip()
                    if not value_filter or value_filter(raw_val):
                        next_sec = (section_map or {}).get(next_idx, sec)
                        candidates.append(AssociatedCandidate(
                            label_text=anchor_label_text,
                            value_text=raw_val,
                            relation=AnchorRelation.BELOW.value,
                            line_index=idx,
                            value_line_index=next_idx,
                            distance=float(offset),
                            confidence=max(0.65, 0.85 - (offset * 0.05)),
                            raw_span=f"{line_clean} \n {next_line}",
                            semantic_section=next_sec,
                        ))
                        break  # Found nearest line candidate

        # 3. SPATIAL OCR ITEM ASSOCIATION (if items with bounding boxes exist)
        if ocr_items:
            for item_idx, item in enumerate(ocr_items):
                item_text = str(item.get('text', '')).strip()
                m_label = label_re.search(item_text)
                if not m_label or not item.get('bbox'):
                    continue

                label_box = item['bbox']
                label_anchor = m_label.group(0).strip()

                # Look for nearby items matching value pattern
                for other_idx, other_item in enumerate(ocr_items):
                    if other_idx == item_idx or not other_item.get('bbox'):
                        continue
                    other_text = str(other_item.get('text', '')).strip()
                    m_val = val_re.search(other_text)
                    if not m_val:
                        continue

                    raw_val = m_val.group(1) if m_val.groups() else m_val.group(0)
                    raw_val = raw_val.strip()
                    if value_filter and not value_filter(raw_val):
                        continue

                    dist, rel = cls._compute_bbox_distance(label_box, other_item['bbox'])
                    # Accept if within reasonable spatial proximity (e.g. distance < 400px)
                    if dist < 400 and rel in (AnchorRelation.RIGHT.value, AnchorRelation.BELOW.value):
                        candidates.append(AssociatedCandidate(
                            label_text=label_anchor,
                            value_text=raw_val,
                            relation=rel,
                            line_index=item.get('line_index', -1),
                            value_line_index=other_item.get('line_index', -1),
                            distance=round(dist, 2),
                            confidence=min(float(item.get('confidence', 0.8)), float(other_item.get('confidence', 0.8))),
                            raw_span=f"{item_text} {other_text}",
                            bounding_box=other_item.get('bbox'),
                            semantic_section="UNKNOWN",
                        ))

        return candidates
