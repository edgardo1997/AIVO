interface Step {
  id: number;
  key: string;
  title: string;
}

interface Props {
  current: number;
  steps: Step[];
}

export function OnboardingProgress({ current, steps }: Props) {
  return (
    <nav aria-label="Progreso del onboarding" className="onboarding-progress">
      <ol role="list">
        {steps.map((step) => (
          <li
            key={step.id}
            className={`onboarding-progress-step ${step.id === current ? "current" : step.id < current ? "completed" : ""
              }`}
            aria-current={step.id === current ? "step" : undefined}
          >
            <span className="onboarding-progress-number" aria-hidden="true">
              {step.id}
            </span>
            <span className="onboarding-progress-title">{step.title}</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
