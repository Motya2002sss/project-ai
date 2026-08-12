import { useRouter } from 'expo-router';

import { OnboardingPreviewScreen } from '../src/features/onboarding/OnboardingPreviewScreen';

export default function OnboardingPreviewRoute() {
  const router = useRouter();
  return (
    <OnboardingPreviewScreen
      onComplete={() => router.replace('/')}
      onEdit={() => router.replace('/onboarding?correction=1')}
      onRequireSignIn={() => router.replace('/sign-in')}
    />
  );
}
