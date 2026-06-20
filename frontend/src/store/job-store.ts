import { create } from 'zustand';
import type { Job, EducationLevel } from './types';

interface JobStore {
  job: Job;
  isAnalyzing: boolean;
  setTitle: (title: string) => void;
  setDepartment: (department: string) => void;
  setDescription: (description: string) => void;
  addMustHaveSkill: (skill: string) => void;
  removeMustHaveSkill: (skill: string) => void;
  addNiceToHaveSkill: (skill: string) => void;
  removeNiceToHaveSkill: (skill: string) => void;
  setMinYears: (years: number) => void;
  setMaxYears: (years: number) => void;
  setEducationLevel: (level: EducationLevel) => void;
  setEducationField: (field: string) => void;
  addKeyword: (keyword: string) => void;
  removeKeyword: (keyword: string) => void;
  setWeight: (key: keyof Job['weights'], value: number) => void;
  setAnalyzing: (analyzing: boolean) => void;
}

export const useJobStore = create<JobStore>((set) => ({
  job: {
    title: '',
    department: '',
    description: '',
    mustHaveSkills: [],
    niceToHaveSkills: [],
    minYears: 0,
    maxYears: 10,
    educationLevel: 'bachelor',
    educationField: '',
    keywords: [],
    weights: {
      skills: 40,
      experience: 25,
      keywords: 20,
      education: 15,
    },
  },
  isAnalyzing: false,

  setTitle: (title) =>
    set((state) => ({ job: { ...state.job, title } })),

  setDepartment: (department) =>
    set((state) => ({ job: { ...state.job, department } })),

  setDescription: (description) =>
    set((state) => ({ job: { ...state.job, description } })),

  addMustHaveSkill: (skill) =>
    set((state) => ({
      job: {
        ...state.job,
        mustHaveSkills: [...state.job.mustHaveSkills, skill],
      },
    })),

  removeMustHaveSkill: (skill) =>
    set((state) => ({
      job: {
        ...state.job,
        mustHaveSkills: state.job.mustHaveSkills.filter((s) => s !== skill),
      },
    })),

  addNiceToHaveSkill: (skill) =>
    set((state) => ({
      job: {
        ...state.job,
        niceToHaveSkills: [...state.job.niceToHaveSkills, skill],
      },
    })),

  removeNiceToHaveSkill: (skill) =>
    set((state) => ({
      job: {
        ...state.job,
        niceToHaveSkills: state.job.niceToHaveSkills.filter((s) => s !== skill),
      },
    })),

  setMinYears: (years) =>
    set((state) => ({ job: { ...state.job, minYears: years } })),

  setMaxYears: (years) =>
    set((state) => ({ job: { ...state.job, maxYears: years } })),

  setEducationLevel: (level) =>
    set((state) => ({ job: { ...state.job, educationLevel: level } })),

  setEducationField: (field) =>
    set((state) => ({ job: { ...state.job, educationField: field } })),

  addKeyword: (keyword) =>
    set((state) => ({
      job: {
        ...state.job,
        keywords: [...state.job.keywords, keyword],
      },
    })),

  removeKeyword: (keyword) =>
    set((state) => ({
      job: {
        ...state.job,
        keywords: state.job.keywords.filter((k) => k !== keyword),
      },
    })),

  setWeight: (key, value) =>
    set((state) => ({
      job: {
        ...state.job,
        weights: { ...state.job.weights, [key]: value },
      },
    })),

  setAnalyzing: (analyzing) => set({ isAnalyzing: analyzing }),
}));
