"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import {
  buildWorkflowHref,
  getActiveWorkflowItem,
  workflowNavItems,
} from "./workflowNavigation";

export function WorkflowSidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeItem = getActiveWorkflowItem(pathname);
  const currentQuery = searchParams.toString();

  return (
    <aside className="rail" aria-label="Workflow navigation">
      <div className="mark" aria-hidden="true">
        ◈
      </div>
      <div>
        <p className="rail-kicker">{activeItem.kicker}</p>
        <p className="rail-title">{activeItem.title}</p>
      </div>
      <nav className="workflow-nav" aria-label="Workflow steps">
        {workflowNavItems.map((item) => {
          const active = item.route === activeItem.route;

          return (
            <Link
              aria-current={active ? "page" : undefined}
              className={active ? "workflow-link active" : "workflow-link"}
              href={buildWorkflowHref(item.route, currentQuery)}
              key={item.route}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="rail-rule" />
      <span className="status-pill">
        <span aria-hidden="true">●</span> {activeItem.status}
      </span>
      <p className="rail-copy">{activeItem.copy}</p>
    </aside>
  );
}
