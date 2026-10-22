import { SignUpForm } from '../../components/auth-forms';
import { SignUpRoleStep } from '../../components/signup-role';

export default function SignUpPage() {
  return <SignUpRoleStep><SignUpForm /></SignUpRoleStep>;
}
