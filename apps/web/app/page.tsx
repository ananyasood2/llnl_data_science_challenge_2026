import { redirect } from "next/navigation";

import { defaultWorkflowRoute } from "./workflowNavigation";

export default function HomePage() {
  redirect(defaultWorkflowRoute);
}
