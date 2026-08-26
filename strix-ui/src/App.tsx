import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useSession } from "./store/session";
import { AppShell } from "./layout/AppShell";
import Login from "./pages/Auth/Login";
import Onboarding from "./pages/Auth/Onboarding";
import Dashboard from "./pages/Dashboard/Dashboard";
import PentestsList from "./pages/Pentests/PentestsList";
import PentestDetail from "./pages/Pentests/PentestDetail";
import IssuesList from "./pages/Issues/IssuesList";
import IssueDetail from "./pages/Issues/IssueDetail";
import PRReviewsList from "./pages/PRReviews/PRReviewsList";
import PRReviewDetail from "./pages/PRReviews/PRReviewDetail";
import RepositoriesList from "./pages/Repositories/RepositoriesList";
import DomainsList from "./pages/Domains/DomainsList";
import DomainDetail from "./pages/Domains/DomainDetail";
import KnowledgeList from "./pages/Knowledge/KnowledgeList";
import IntegrationsList from "./pages/Integrations/IntegrationsList";
import NetworksList from "./pages/Networks/NetworksList";
import Chat from "./pages/Chat/Chat";
import { SettingsLayout } from "./pages/Settings/SettingsLayout";
import GeneralSettings from "./pages/Settings/GeneralSettings";
import LlmProviderSettings from "./pages/Settings/LlmProviderSettings";
import MembersSettings from "./pages/Settings/MembersSettings";
import ApiAccessSettings from "./pages/Settings/ApiAccessSettings";
import BillingSettings from "./pages/Settings/BillingSettings";
import AuditLogsSettings from "./pages/Settings/AuditLogsSettings";
import HelpSupportSettings from "./pages/Settings/HelpSupportSettings";

export default function App() {
  const refresh = useSession((s) => s.refresh);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/onboarding" element={<Onboarding />} />

      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/pentests" element={<PentestsList />} />
        <Route path="/pentests/:id" element={<PentestDetail />} />
        <Route path="/issues" element={<IssuesList />} />
        <Route path="/issues/:id" element={<IssueDetail />} />
        <Route path="/pr-reviews" element={<PRReviewsList />} />
        <Route path="/pr-reviews/:id" element={<PRReviewDetail />} />
        <Route path="/repositories" element={<RepositoriesList />} />
        <Route path="/domains" element={<DomainsList />} />
        <Route path="/domains/:id" element={<DomainDetail />} />
        <Route path="/networks" element={<NetworksList />} />
        <Route path="/knowledge" element={<KnowledgeList />} />
        <Route path="/integrations" element={<IntegrationsList />} />
        <Route path="/chat" element={<Chat />} />

        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<GeneralSettings />} />
          <Route path="llm-provider" element={<LlmProviderSettings />} />
          <Route path="members" element={<MembersSettings />} />
          <Route path="api-access" element={<ApiAccessSettings />} />
          <Route path="billing" element={<BillingSettings />} />
          <Route path="audit-logs" element={<AuditLogsSettings />} />
          <Route path="help-support" element={<HelpSupportSettings />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
