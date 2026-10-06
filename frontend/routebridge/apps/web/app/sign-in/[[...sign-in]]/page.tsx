import { AuthAttemptGate } from '../../../components/auth-attempt-gate';

export default function SignInPage() {
  return <AuthAttemptGate mode="signin" />;
}
