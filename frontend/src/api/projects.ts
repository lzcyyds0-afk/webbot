import client from './client';
import type { Project, ProjectCreate } from '../types';

export const fetchProjects = () =>
  client.get<Project[]>('/projects').then((r) => r.data);

export const fetchProject = (id: number) =>
  client.get<Project>(`/projects/${id}`).then((r) => r.data);

export const createProject = (data: ProjectCreate) =>
  client.post<Project>('/projects', data).then((r) => r.data);

export const deleteProject = (id: number) =>
  client.delete(`/projects/${id}`).then((r) => r.data);
