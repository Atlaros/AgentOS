import { SignupForm } from "./signup-form";

export default function SignupPage() {
  return (
    <section className="login-card">
      <h1>Alta de negocio</h1>
      <p className="lead">Creá tu negocio con la invitación que te dio el operador.</p>
      <SignupForm />
    </section>
  );
}
