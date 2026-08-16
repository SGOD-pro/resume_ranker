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
    title: 'Senior Data Scientist',
    department: 'Data Analytics',
    description: 'We are looking for an experienced Data Scientist to lead our machine learning initiatives, build predictive models, and extract actionable insights from large datasets. The ideal candidate has a strong background in statistics, programming, and deploying models to production.',
    mustHaveSkills: ['Python', 'Machine Learning', 'SQL', 'TensorFlow', 'Pandas'],
    niceToHaveSkills: ['AWS', 'Docker', 'Kubernetes', 'PyTorch'],
    minYears: 3,
    maxYears: 8,
    educationLevel: 'bachelor',
    educationField: 'Computer Science, Statistics, or related',
    keywords: ['Predictive Modeling', 'Data Visualization', 'A/B Testing', 'NLP'],
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
