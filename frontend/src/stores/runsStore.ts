import { create } from 'zustand';
import type { Run, RunStep, WsMessage, StepDetails, StepDiagnosis } from '../types';
import * as runsApi from '../api/runs';

interface RunsState {
  currentRun: Run | null;
  steps: RunStep[];
  activeStepIndex: number;
  loading: boolean;
  stepDetails: Record<string, StepDetails>; // key: `${runId}-${stepIndex}`
  stepDetailsLoading: Record<string, boolean>;
  stepDiagnoses: Record<string, StepDiagnosis | null>; // key: `${runId}-${stepIndex}`
  stepDiagnosesLoading: Record<string, boolean>;

  fetchRun: (id: number) => Promise<void>;
  fetchSteps: (runId: number) => Promise<void>;
  fetchStepDetails: (runId: number, stepIndex: number) => Promise<void>;
  fetchStepDiagnosis: (runId: number, stepIndex: number) => Promise<void>;
  runAiDiagnosis: (runId: number, stepIndex: number, llmConfigId?: number) => Promise<void>;
  setActiveStepIndex: (i: number) => void;
  handleWsMessage: (msg: WsMessage) => void;
  reset: () => void;
}

const detailsKey = (runId: number, stepIndex: number) => `${runId}-${stepIndex}`;

export const useRunsStore = create<RunsState>((set, get) => ({
  currentRun: null,
  steps: [],
  activeStepIndex: 0,
  loading: false,
  stepDetails: {},
  stepDetailsLoading: {},
  stepDiagnoses: {},
  stepDiagnosesLoading: {},

  fetchRun: async (id) => {
    set({ loading: true });
    try {
      const run = await runsApi.fetchRun(id);
      set({ currentRun: run });
    } finally {
      set({ loading: false });
    }
  },

  fetchSteps: async (runId) => {
    set({ loading: true });
    try {
      const steps = await runsApi.fetchRunSteps(runId);
      // Only replace if we got real data; preserve WS placeholder steps if API returned empty
      if (steps.length > 0) {
        set({ steps });
      }
    } catch (err) {
      console.error('fetchSteps failed:', err);
    } finally {
      set({ loading: false });
    }
  },

  fetchStepDetails: async (runId, stepIndex) => {
    const key = detailsKey(runId, stepIndex);
    set((state) => ({ stepDetailsLoading: { ...state.stepDetailsLoading, [key]: true } }));
    try {
      const details = await runsApi.fetchStepDetails(runId, stepIndex);
      set((state) => ({
        stepDetails: { ...state.stepDetails, [key]: details },
      }));
    } catch (err) {
      console.error('fetchStepDetails failed:', err);
    } finally {
      set((state) => ({ stepDetailsLoading: { ...state.stepDetailsLoading, [key]: false } }));
    }
  },

  fetchStepDiagnosis: async (runId, stepIndex) => {
    const key = detailsKey(runId, stepIndex);
    set((state) => ({ stepDiagnosesLoading: { ...state.stepDiagnosesLoading, [key]: true } }));
    try {
      const diagnosis = await runsApi.fetchStepDiagnosis(runId, stepIndex);
      set((state) => ({
        stepDiagnoses: { ...state.stepDiagnoses, [key]: diagnosis },
      }));
    } catch (err) {
      console.error('fetchStepDiagnosis failed:', err);
      set((state) => ({
        stepDiagnoses: { ...state.stepDiagnoses, [key]: null },
      }));
    } finally {
      set((state) => ({ stepDiagnosesLoading: { ...state.stepDiagnosesLoading, [key]: false } }));
    }
  },

  runAiDiagnosis: async (runId, stepIndex, llmConfigId) => {
    const key = detailsKey(runId, stepIndex);
    set((state) => ({ stepDiagnosesLoading: { ...state.stepDiagnosesLoading, [key]: true } }));
    try {
      const diagnosis = await runsApi.runAiDiagnosis(runId, stepIndex, llmConfigId);
      set((state) => ({
        stepDiagnoses: { ...state.stepDiagnoses, [key]: diagnosis },
      }));
    } catch (err) {
      console.error('runAiDiagnosis failed:', err);
    } finally {
      set((state) => ({ stepDiagnosesLoading: { ...state.stepDiagnosesLoading, [key]: false } }));
    }
  },

  setActiveStepIndex: (i) => set({ activeStepIndex: i }),

  handleWsMessage: (msg) => {
    const { currentRun, steps } = get();

    if (msg.event === 'step_start') {
      // Highlight the step that just started
      set({ activeStepIndex: msg.step_index ?? 0 });
      if (msg.step_index !== null) {
        const existing = steps.find((s) => s.step_index === msg.step_index);
        if (existing) {
          set({
            steps: steps.map((s) =>
              s.step_index === msg.step_index
                ? {
                    ...s,
                    status: 'running' as RunStep['status'],
                    screenshot_path: msg.screenshot_url ?? s.screenshot_path,
                    action: msg.action ?? s.action,
                    params_summary: msg.params_summary ?? s.params_summary,
                  }
                : s,
            ),
          });
        } else {
          // Step not in array yet (fetchSteps returned before DB write) — add placeholder
          set({
            steps: [
              ...steps,
              {
                id: 0,
                run_id: msg.run_id,
                step_index: msg.step_index,
                action: msg.action ?? '',
                params_summary: msg.params_summary ?? null,
                input_json: null,
                output_json: null,
                screenshot_path: msg.screenshot_url ?? null,
                status: 'running' as RunStep['status'],
                duration_ms: null,
                error: null,
              },
            ],
          });
        }
      }
    }

    if (msg.event === 'step_end') {
      if (msg.step_index !== null) {
        const existing = steps.find((s) => s.step_index === msg.step_index);
        if (existing) {
          set({
            steps: steps.map((s) =>
              s.step_index === msg.step_index
                ? {
                    ...s,
                    status: msg.status as RunStep['status'],
                    error: msg.error ?? s.error,
                    screenshot_path: msg.screenshot_url ?? s.screenshot_path,
                    action: msg.action ?? s.action,
                    duration_ms: msg.duration_ms ?? s.duration_ms,
                    params_summary: msg.params_summary ?? s.params_summary,
                  }
                : s,
            ),
          });
        } else {
          // Add completed step from WS message
          set({
            steps: [
              ...steps,
              {
                id: 0,
                run_id: msg.run_id,
                step_index: msg.step_index,
                action: msg.action ?? '',
                params_summary: msg.params_summary ?? null,
                input_json: null,
                output_json: null,
                screenshot_path: msg.screenshot_url ?? null,
                status: msg.status as RunStep['status'],
                duration_ms: msg.duration_ms ?? null,
                error: msg.error ?? null,
              },
            ],
          });
        }
        // Cache enriched details from WS if available
        if (msg.console_logs || msg.network_requests || msg.dom_snippet || msg.target_bbox) {
          const key = detailsKey(msg.run_id, msg.step_index);
          set((state) => ({
            stepDetails: {
              ...state.stepDetails,
              [key]: {
                console_logs: msg.console_logs ?? [],
                network_requests: msg.network_requests ?? [],
                dom_snippet: msg.dom_snippet ?? null,
                target_bbox: msg.target_bbox ?? null,
              },
            },
          }));
        }
      }
    }

    if (msg.event === 'heal_notice') {
      if (msg.step_index !== null) {
        set({
          steps: steps.map((s) =>
            s.step_index === msg.step_index
              ? {
                  ...s,
                  status: 'passed' as RunStep['status'],
                  params_summary: msg.params_summary ?? s.params_summary,
                  output_json: {
                    ...(s.output_json || {}),
                    healed: true,
                    healed_selector: msg.healed_selector,
                    original_selector: msg.original_selector,
                  },
                }
              : s,
          ),
        });
      }
    }

    if (msg.event === 'run_end') {
      if (currentRun) {
        set({
          currentRun: { ...currentRun, status: msg.status as Run['status'] },
        });
      }
      // Refresh steps and run from API to get final persisted data (screenshot_path, duration_ms, narrative, etc.)
      get().fetchSteps(msg.run_id);
      get().fetchRun(msg.run_id);
    }
  },

  reset: () => set({ currentRun: null, steps: [], activeStepIndex: 0, stepDetails: {}, stepDetailsLoading: {}, stepDiagnoses: {}, stepDiagnosesLoading: {} }),
}));
