import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import ErrorBoundary from './components/ErrorBoundary';
import ProjectsPage from './pages/ProjectsPage';
import ProjectDetailPage from './pages/ProjectDetailPage';
import ProjectReportPage from './pages/ProjectReportPage';
import RunDetailPage from './pages/RunDetailPage';
import LLMSettingsPage from './pages/LLMSettingsPage';

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectDetailPage />} />
            <Route path="/projects/:id/report" element={<ProjectReportPage />} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
            <Route path="/settings/llm" element={<LLMSettingsPage />} />
          </Route>
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
