import Link from "next/link";
import {
  getWorkflowStepAriaCurrent,
  isWorkflowStepNavigable,
  type WorkflowStep,
  type WorkflowStepId,
  type WorkflowStepState,
} from "./workflowNavigation";
export {
  buildWorkflowHref,
  getWorkflowStepAriaCurrent,
  isWorkflowStepNavigable,
  type WorkflowStep,
} from "./workflowNavigation";

const workflowStepContent: Record<
  WorkflowStepId,
  { step: string; title: string; summary: string }
> = {
  "project-dataset": {
    step: "Step 1",
    title: "Project / Dataset",
    summary: "Define project context and select source CT data.",
  },
  segmentation: {
    step: "Step 2",
    title: "CT Preparation",
    summary: "Review slices, tune threshold, and save the final mask.",
  },
  "structure-analysis": {
    step: "Step 3",
    title: "3D Structure Analysis",
    summary: "Validate the prepared structure outputs.",
  },
};

const stateLabels: Record<WorkflowStepState, string> = {
  active: "Current",
  completed: "Complete",
  available: "Available",
  locked: "Locked",
};

export function WorkflowSidebar({ steps }: { steps: WorkflowStep[] }) {
  const activeStep = steps.find((step) => step.state === "active");
  const activeContent = activeStep ? workflowStepContent[activeStep.id] : null;

  return (
    <aside className="rail workflow-rail" aria-label="Workflow navigation">
      <div className="workflow-rail-header">
        <div className="mark" aria-hidden="true">
          ◈
        </div>
        <div>
          <p className="rail-kicker">{activeContent?.step ?? "Workflow"}</p>
          <p className="rail-title">{activeContent?.title ?? "Analysis workflow"}</p>
        </div>
      </div>
      <div className="rail-rule" />
      <nav aria-label="Workflow steps">
        <ol className="workflow-steps">
          {steps.map((step) => {
            const content = workflowStepContent[step.id];
            const className = `workflow-step workflow-step-${step.state}`;
            const inner = (
              <>
                <span className="workflow-step-index" aria-hidden="true">
                  {content.step.replace("Step ", "")}
                </span>
                <span className="workflow-step-body">
                  <span className="workflow-step-title">{content.title}</span>
                  <span className="workflow-step-summary">{content.summary}</span>
                </span>
                <span className="workflow-step-state">{stateLabels[step.state]}</span>
              </>
            );

            return (
              <li key={step.id}>
                {isWorkflowStepNavigable(step) ? (
                  <Link
                    className={className}
                    href={step.href ?? "#"}
                    aria-current={getWorkflowStepAriaCurrent(step.state)}
                  >
                    {inner}
                  </Link>
                ) : (
                  <button
                    className={className}
                    type="button"
                    disabled
                    aria-current={getWorkflowStepAriaCurrent(step.state)}
                  >
                    {inner}
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
    </aside>
  );
}
