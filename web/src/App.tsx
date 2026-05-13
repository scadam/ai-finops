import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import AgentExplorer from "@/pages/AgentExplorer";
import WhatIfModeler from "@/pages/WhatIfModeler";
import RequirementModeler from "@/pages/RequirementModeler";
import Optimisations from "@/pages/Optimisations";
import Governance from "@/pages/Governance";
import NotFound from "@/pages/NotFound";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "agents", element: <AgentExplorer /> },
      { path: "modeler", element: <WhatIfModeler /> },
      { path: "design", element: <RequirementModeler /> },
      { path: "optimisations", element: <Optimisations /> },
      { path: "governance", element: <Governance /> },
      { path: "dashboard", element: <Navigate to="/" replace /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
