import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Check, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field } from "@/components/app/common";
import { Brand } from "@/layouts/AppLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api, errorMessage } from "@/lib/api";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-muted/30 p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="flex justify-center"><Brand /></div>
        {children}
        <p className="text-center text-xs text-muted-foreground">You always submit applications yourself on the original job site.</p>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Sign-in failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <Card>
        <CardHeader><CardTitle>Sign in</CardTitle><CardDescription>Welcome back. Pick up where you left off.</CardDescription></CardHeader>
        <form onSubmit={submit}>
          <CardContent className="space-y-4">
            {error && <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
            <Field label="Email" htmlFor="email"><Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Field label="Password" htmlFor="password"><Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            <p className="text-xs text-muted-foreground">Forgot your password? Password reset by email is not available yet. Ask the portal owner to reset your account.</p>
          </CardContent>
          <CardFooter className="mt-4 flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={busy}>{busy && <Loader2 className="animate-spin" />} Sign in</Button>
            <p className="text-sm text-muted-foreground">New here? <Link to="/register" className="font-medium text-foreground underline">Create an account</Link></p>
          </CardFooter>
        </form>
      </Card>
    </Shell>
  );
}

const rules: { test: (p: string, e: string) => boolean; label: string }[] = [
  { test: (p) => p.length >= 10, label: "At least 10 characters" },
  { test: (p) => /[a-z]/.test(p) && /[A-Z]/.test(p), label: "Upper- and lower-case letters" },
  { test: (p) => /\d/.test(p), label: "At least one number" },
  { test: (p, e) => { const n = e.split("@")[0].toLowerCase(); return !(n.length >= 4 && p.toLowerCase().includes(n)); }, label: "Doesn't contain your email name" },
];

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", confirm: "", invite_code: "" });
  const [needsInvite, setNeedsInvite] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<{ registration_requires_invite: boolean }>("/auth/config").then((r) => setNeedsInvite(r.data.registration_requires_invite)).catch(() => {});
  }, []);

  const passed = rules.map((r) => r.test(form.password, form.email));
  const valid = passed.every(Boolean) && form.password === form.confirm && form.email.includes("@");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await register({ email: form.email, password: form.password, full_name: form.full_name || undefined, invite_code: form.invite_code || undefined });
      navigate("/onboarding", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Registration failed"));
    } finally {
      setBusy(false);
    }
  };
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  return (
    <Shell>
      <Card>
        <CardHeader><CardTitle>Create your account</CardTitle><CardDescription>Your resume, preferences and applications stay private to your account.</CardDescription></CardHeader>
        <form onSubmit={submit}>
          <CardContent className="space-y-4">
            {error && <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
            <Field label="Full name" htmlFor="name"><Input id="name" autoComplete="name" value={form.full_name} onChange={set("full_name")} /></Field>
            <Field label="Email" htmlFor="remail"><Input id="remail" type="email" autoComplete="email" required value={form.email} onChange={set("email")} /></Field>
            <Field label="Password" htmlFor="rpass"><Input id="rpass" type="password" autoComplete="new-password" required value={form.password} onChange={set("password")} /></Field>
            <ul className="grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
              {rules.map((r, i) => (
                <li key={r.label} className={`flex items-center gap-1 ${passed[i] ? "text-emerald-600" : "text-muted-foreground"}`}>{passed[i] ? <Check className="size-3" /> : <X className="size-3" />}{r.label}</li>
              ))}
            </ul>
            <Field label="Confirm password" htmlFor="rconf" hint={form.confirm && form.confirm !== form.password ? "Passwords don't match" : undefined}>
              <Input id="rconf" type="password" autoComplete="new-password" required value={form.confirm} onChange={set("confirm")} />
            </Field>
            {needsInvite && <Field label="Invite code" htmlFor="invite" hint="This portal is invite-only. Ask the owner for a code."><Input id="invite" required value={form.invite_code} onChange={set("invite_code")} /></Field>}
          </CardContent>
          <CardFooter className="mt-4 flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={busy || !valid}>{busy && <Loader2 className="animate-spin" />} Create account</Button>
            <p className="text-sm text-muted-foreground">Already registered? <Link to="/login" className="font-medium text-foreground underline">Sign in</Link></p>
          </CardFooter>
        </form>
      </Card>
    </Shell>
  );
}
