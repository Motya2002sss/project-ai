export const motion = {
  quick: 160,
  settle: 320,
} as const;

export function modalAnimationType(reduceMotion: boolean): 'none' | 'slide' {
  return reduceMotion ? 'none' : 'slide';
}
