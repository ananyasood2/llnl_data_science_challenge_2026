export const defaultWorkflowRoute = "/project-dataset";

export type WorkflowRoute =
  | "/project-dataset"
  | "/segmentation"
  | "/structure-analysis";

export type WorkflowNavItem = {
  label: string;
  route: WorkflowRoute;
  kicker: string;
  title: string;
  status: string;
  copy: string;
};

export const workflowNavItems: WorkflowNavItem[] = [
  {
    label: "Project / Dataset",
    route: "/project-dataset",
    kicker: "Step 1",
    title: "Project / Dataset",
    status: "Intake scaffold",
    copy:
      "Define the inspection project and select the dataset that will feed the segmentation and skeletonization pipeline.",
  },
  {
    label: "CT Preparation",
    route: "/segmentation",
    kicker: "Step 2",
    title: "CT Preparation",
    status: "Preview scaffold",
    copy:
      "Inspect slices, tune a lightweight threshold preview, and prepare the final segmentation result for the 3D Structure Analysis page.",
  },
  {
    label: "3D Structure Analysis",
    route: "/structure-analysis",
    kicker: "Step 3",
    title: "3D Structure Analysis",
    status: "Dash viewer",
    copy:
      "Validate the prepared CT segmentation using the existing 3D Dash dashboard.",
  },
];

export function getActiveWorkflowItem(pathname: string) {
  return (
    workflowNavItems.find((item) => pathname.startsWith(item.route)) ??
    workflowNavItems[0]
  );
}

export function buildWorkflowHref(route: WorkflowRoute, currentQuery?: string) {
  const query = currentQuery?.replace(/^\?/, "").trim();

  return query ? `${route}?${query}` : route;
}
