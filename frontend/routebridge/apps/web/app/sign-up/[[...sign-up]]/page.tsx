import { AuthAttemptGate } from '../../../components/auth-attempt-gate';

export default function SignUpPage() {
  return <AuthAttemptGate mode="signup" />;
}
