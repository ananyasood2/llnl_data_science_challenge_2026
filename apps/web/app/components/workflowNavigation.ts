export type WorkflowStepId = "project-dataset" | "segmentation" | "structure-analysis";

export type WorkflowStepState = "active" | "completed" | "available" | "locked";

export type WorkflowStep = {
  id: WorkflowStepId;
  href: string | null;
  state: WorkflowStepState;
};

export function buildWorkflowHref(
  pathname: "/project-dataset" | "/segmentation" | "/structure-analysis",
  params?: URLSearchParams | string | null,
) {
  const query = params?.toString();
  return query ? `${pathname}?${query}` : pathname;
}

export function getWorkflowStepAriaCurrent(state: WorkflowStepState) {
  return state === "active" ? "page" : undefined;
}

export function isWorkflowStepNavigable(step: WorkflowStep) {
  return Boolean(step.href) && step.state !== "locked";
}
