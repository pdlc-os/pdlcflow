import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import './lib/theme.css';
import './main.css';
import { applyTheme, getStoredTheme, watchSystemTheme } from './lib/theme';
import { AppShell } from './routes/AppShell';
import { ProjectSwitcher } from './routes/index';
import { ProjectView } from './routes/projects/[id]';
import { AdminLayout } from './routes/admin/layout';
import { AdminLive } from './routes/admin/live';
import { AdminInitiatives } from './routes/admin/initiatives';
import { AdminDomains } from './routes/admin/domains';
import { AdminSquads } from './routes/admin/squads';
import { AdminAgents } from './routes/admin/agents';
import { AdminFeatures } from './routes/admin/features';
import { AdminExports } from './routes/admin/exports';
import { AdminModels } from './routes/admin/models';
import { AdminPrompts } from './routes/admin/prompts';
import { AdminMCP } from './routes/admin/mcp';
import { AdminNarrative } from './routes/admin/narrative';

applyTheme(getStoredTheme());
watchSystemTheme(() => applyTheme(getStoredTheme()));

const qc = new QueryClient();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<ProjectSwitcher />} />
            <Route path="/projects/:id" element={<ProjectView />} />
            <Route path="/admin" element={<AdminLayout />}>
              <Route path="live" element={<AdminLive />} />
              <Route path="initiatives" element={<AdminInitiatives />} />
              <Route path="domains" element={<AdminDomains />} />
              <Route path="squads" element={<AdminSquads />} />
              <Route path="agents" element={<AdminAgents />} />
              <Route path="features" element={<AdminFeatures />} />
              <Route path="features/:f" element={<AdminFeatures />} />
              <Route path="narrative" element={<AdminNarrative />} />
              <Route path="exports" element={<AdminExports />} />
              <Route path="models" element={<AdminModels />} />
              <Route path="prompts" element={<AdminPrompts />} />
              <Route path="mcp" element={<AdminMCP />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
