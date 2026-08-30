# Requirement Refinement During Testing

## Original requirement

Create a management warning when the absolute month-over-month movement in New Customers is greater than 20%.

## Testing result

The implementation produced 147 warnings because branch-level New Customer counts were often small. For example, a change from 1 to 2 customers is a 100% increase even though the absolute change is only one customer. The SQL was correctly implementing the requirement, but the result was operationally noisy.

## Refined requirement

Create a New Customers warning only when both conditions are met:

- absolute month-over-month percentage change is greater than 20%; and
- absolute count change is at least 5 customers.

If the previous value is missing or zero, the percentage change remains NULL rather than becoming an infinite percentage.

The refined rule produces 3 warnings in the synthetic dataset and retains the intended injected warning scenario.

## Business-analysis lesson

This is a traceable cycle of requirement → implementation → testing → observed operational problem → requirement refinement. The original requirement was not a coding bug. Testing showed that a percentage-only threshold did not match the practical review need when volumes were small.
