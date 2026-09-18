import React from 'react';
import { Check } from 'lucide-react';
import './ProgressStepper.css';

/**
 * 5-Stage Inspection Progress Stepper
 * Steps:
 * 1: Capture Package
 * 2: Review Images
 * 3: Analyze Evidence
 * 4: Compliance Results
 * 5: Report
 */
const STEPS = [
  { id: 1, title: 'Capture Package', short: 'Capture' },
  { id: 2, title: 'Review Images', short: 'Review' },
  { id: 3, title: 'Analyze Evidence', short: 'Analyze' },
  { id: 4, title: 'Compliance Results', short: 'Compliance' },
  { id: 5, title: 'Inspection Report', short: 'Report' },
];

const ProgressStepper = ({ currentStep = 1, className = '' }) => {
  return (
    <div className={`progress-stepper ${className}`} aria-label="Inspection Workflow Progress">
      <div className="progress-stepper__track">
        {STEPS.map((step, idx) => {
          const isCompleted = currentStep > step.id;
          const isCurrent = currentStep === step.id;
          const isPending = currentStep < step.id;

          let stateClass = 'pending';
          if (isCompleted) stateClass = 'completed';
          if (isCurrent) stateClass = 'current';

          return (
            <React.Fragment key={step.id}>
              <div
                className={`stepper-node stepper-node--${stateClass}`}
                aria-current={isCurrent ? 'step' : undefined}
              >
                <div className="stepper-node__circle">
                  {isCompleted ? (
                    <Check size={14} strokeWidth={3} className="stepper-check" />
                  ) : (
                    <span>{step.id}</span>
                  )}
                </div>
                <div className="stepper-node__content">
                  <span className="stepper-node__step-num">Step {step.id}</span>
                  <span className="stepper-node__title">{step.title}</span>
                </div>
              </div>
              {idx < STEPS.length - 1 && (
                <div
                  className={`stepper-connector ${
                    currentStep > step.id ? 'stepper-connector--completed' : ''
                  }`}
                  aria-hidden="true"
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

export default ProgressStepper;
