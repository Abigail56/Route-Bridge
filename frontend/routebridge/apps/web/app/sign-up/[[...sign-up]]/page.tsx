import { AuthAttemptGate } from '../../../components/auth-attempt-gate';
import { SignUpRoleStep } from '../../../components/signup-role';

export default function SignUpPage() {
  return <SignUpRoleStep><AuthAttemptGate mode="signup" /></SignUpRoleStep>;
}
