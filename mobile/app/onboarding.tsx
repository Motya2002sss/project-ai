import { useLocalSearchParams, useRouter } from 'expo-router';

import { OnboardingScreen } from '../src/features/onboarding/OnboardingScreen';

export default function OnboardingRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ correction?: string; textOnly?: string }>();
  return (
    <OnboardingScreen
      editing={params.correction === '1'}
      onCompleted={() => router.replace('/')}
      onPreviewReady={() => router.replace('/onboarding-preview')}
      onRequireSignIn={() => router.replace('/sign-in')}
      textOnly={params.textOnly === '1'}
    />
  );
}
