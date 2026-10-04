import { redirect } from "next/navigation";

// Free credits belong to a verified account; a resume email is not proof of identity.
export default function FreeTrialPage() {
  redirect("/auth/signup?callbackUrl=%2Fsession%2Fnew");
}
