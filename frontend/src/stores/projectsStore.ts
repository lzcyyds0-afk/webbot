import { create } from 'zustand';
import type { Project, ProjectCreate, TestCase, TestCaseCreate, StepDef } from '../types';
import * as projectsApi from '../api/projects';
import * as testCasesApi from '../api/testCases';

interface ProjectsState {
  projects: Project[];
  currentProject: Project | null;
  testCases: TestCase[];
  currentTestCase: TestCase | null;
  loading: boolean;

  fetchProjects: () => Promise<void>;
  fetchProject: (id: number) => Promise<Project>;
  createProject: (data: ProjectCreate) => Promise<Project>;
  deleteProject: (id: number) => Promise<void>;
  setCurrentProject: (p: Project | null) => void;

  fetchTestCases: (projectId: number) => Promise<void>;
  createTestCase: (projectId: number, data: TestCaseCreate) => Promise<TestCase>;
  deleteTestCase: (projectId: number, caseId: number) => Promise<void>;
  setCurrentTestCase: (c: TestCase | null) => void;
  updateTestCaseSteps: (projectId: number, caseId: number, steps: StepDef[], cookies?: TestCase['cookies_json']) => Promise<void>;
}

export const useProjectsStore = create<ProjectsState>((set, get) => ({
  projects: [],
  currentProject: null,
  testCases: [],
  currentTestCase: null,
  loading: false,

  fetchProjects: async () => {
    set({ loading: true });
    try {
      const projects = await projectsApi.fetchProjects();
      set({ projects });
    } finally {
      set({ loading: false });
    }
  },

  fetchProject: async (id) => {
    const project = await projectsApi.fetchProject(id);
    set({ currentProject: project });
    return project;
  },

  createProject: async (data) => {
    const project = await projectsApi.createProject(data);
    set({ projects: [...get().projects, project] });
    return project;
  },

  deleteProject: async (id) => {
    await projectsApi.deleteProject(id);
    set({ projects: get().projects.filter((p) => p.id !== id) });
  },

  setCurrentProject: (p) => set({ currentProject: p }),

  fetchTestCases: async (projectId) => {
    set({ loading: true });
    try {
      const testCases = await testCasesApi.fetchTestCases(projectId);
      set({ testCases });
    } finally {
      set({ loading: false });
    }
  },

  createTestCase: async (projectId, data) => {
    const tc = await testCasesApi.createTestCase(projectId, data);
    set({ testCases: [...get().testCases, tc] });
    return tc;
  },

  deleteTestCase: async (projectId, caseId) => {
    await testCasesApi.deleteTestCase(projectId, caseId);
    set({ testCases: get().testCases.filter((tc) => tc.id !== caseId) });
  },

  setCurrentTestCase: (c) => set({ currentTestCase: c }),

  updateTestCaseSteps: async (projectId, caseId, steps, cookies) => {
    const updated = await testCasesApi.updateTestCaseSteps(projectId, caseId, steps, cookies);
    set({
      testCases: get().testCases.map((tc) => (tc.id === caseId ? updated : tc)),
      currentTestCase: updated,
    });
  },
}));