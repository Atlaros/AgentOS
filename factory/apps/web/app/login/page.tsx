import { LoginForm } from "./login-form";

interface LoginPageProps {
  searchParams: Promise<{ next?: string }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { next } = await searchParams;
  const redirectTo = next?.startsWith("/") && !next.startsWith("//") ? next : "/";
  return (
    <section className="login-card">
      <h1>Panel del dueño</h1>
      <p className="lead">Inicia sesión con tu usuario del panel.</p>
      <LoginForm redirectTo={redirectTo} />
    </section>
  );
}
