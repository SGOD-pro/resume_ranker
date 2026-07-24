import { create } from 'zustand';

interface Weights {
  skills: number;
  experience: number;
  education: number;
  semantic: number;
}

interface WeightsStore {
  weights: Weights;
  setWeight: (key: keyof Weights, value: number) => void;
  computeComposite: (candidate: { 
    skill_score?: number; 
    experience_score?: number; 
    education_score?: number; 
    semantic_score?: number;
  }) => number;
}

export const useWeightsStore = create<WeightsStore>((set, get) => ({
  weights: {
    skills: 40,
    experience: 25,
    education: 15,
    semantic: 20,
  },

  setWeight: (key, value) =>
    set((state) => ({
      weights: { ...state.weights, [key]: value },
    })),

  computeComposite: (candidate) => {
    const { weights } = get();
    
    // Calculate sum of weights
    const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0);
    
    if (totalWeight === 0) return 0;

    // Normalize weights so they sum to 1.0
    const wSkills = weights.skills / totalWeight;
    const wExp = weights.experience / totalWeight;
    const wEdu = weights.education / totalWeight;
    const wSem = weights.semantic / totalWeight;

    // Get candidate scores (default to 0 if missing)
    const sSkills = candidate.skill_score || 0;
    const sExp = candidate.experience_score || 0;
    const sEdu = candidate.education_score || 0;
    const sSem = candidate.semantic_score || 0;

    // Calculate weighted sum
    return (sSkills * wSkills) + (sExp * wExp) + (sEdu * wEdu) + (sSem * wSem);
  },
}));
