/**
 * Date and time formatting utilities for LMAI Inspector.
 * All timestamps from the backend are stored in UTC and are formatted
 * explicitly in Indian Standard Time (IST - Asia/Kolkata / UTC+05:30).
 */

/**
 * Safely parses a server date string, timestamp, or Date object.
 * If given an ISO-8601 string without a timezone designator (no 'Z' and no '+/-offset'),
 * treats it as UTC by appending 'Z', avoiding browser-local assumption of UTC timestamps.
 * 
 * @param {string|number|Date} dateInput 
 * @returns {Date|null}
 */
export function parseServerDate(dateInput) {
  if (!dateInput) return null;
  if (dateInput instanceof Date) {
    return isNaN(dateInput.getTime()) ? null : dateInput;
  }
  if (typeof dateInput === 'number') {
    const d = new Date(dateInput);
    return isNaN(d.getTime()) ? null : d;
  }
  if (typeof dateInput === 'string') {
    let s = dateInput.trim();
    if (!s) return null;
    // If ISO datetime without timezone indicator (e.g. 2026-09-07T10:44:18 or 2026-09-07 10:44:18)
    if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}/.test(s)) {
      if (s.includes(' ') && !s.includes('T')) {
        s = s.replace(' ', 'T');
      }
      if (!s.endsWith('Z') && !/[+-]\d{2}(:\d{2})?$/.test(s)) {
        s += 'Z';
      }
    }
    const d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }
  return null;
}

/**
 * Formats a timestamp into an IST date and time string.
 * Example: "07 Sep 2026, 04:15:23 PM IST"
 * 
 * @param {string|number|Date} dateInput
 * @param {Object} options
 * @returns {string}
 */
export function formatISTDateTime(dateInput, { includeSeconds = true, includeIST = true } = {}) {
  const date = parseServerDate(dateInput);
  if (!date) return '—';

  const options = {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' } : {}),
    hour12: true,
  };

  const formatted = new Intl.DateTimeFormat('en-IN', options)
    .format(date)
    .replace(/\b(am|pm)\b/gi, (m) => m.toUpperCase());

  return includeIST ? `${formatted} IST` : formatted;
}

/**
 * Formats a timestamp into an IST date string.
 * Example: "07 Sep 2026"
 * 
 * @param {string|number|Date} dateInput
 * @returns {string}
 */
export function formatISTDate(dateInput) {
  const date = parseServerDate(dateInput);
  if (!date) return '—';

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

/**
 * Formats a timestamp into an IST time string.
 * Example: "04:15 PM IST"
 * 
 * @param {string|number|Date} dateInput
 * @param {Object} options
 * @returns {string}
 */
export function formatISTTime(dateInput, { includeSeconds = false, includeIST = true } = {}) {
  const date = parseServerDate(dateInput);
  if (!date) return '—';

  const options = {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' } : {}),
    hour12: true,
  };

  const formatted = new Intl.DateTimeFormat('en-IN', options)
    .format(date)
    .replace(/\b(am|pm)\b/gi, (m) => m.toUpperCase());

  return includeIST ? `${formatted} IST` : formatted;
}
