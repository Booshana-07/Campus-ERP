/**
 * Phase 3A — password rules, mirrored from the backend (app/security.py).
 *
 * This exists for instant feedback while typing. It is NOT a security control:
 * the backend re-validates every password itself and is the authority. Keep the
 * two in sync — if you change a rule here, change it in app/security.py too.
 */

export const PASSWORD_MIN_LENGTH = 8;

const SPECIAL_CHARACTERS = "!@#$%^&*()-_=+[]{};:'\",.<>/?\\|`~";

export const PASSWORD_RULES = [
  {
    id: "length",
    label: `At least ${PASSWORD_MIN_LENGTH} characters`,
    test: (pw) => pw.length >= PASSWORD_MIN_LENGTH,
  },
  { id: "upper", label: "One uppercase letter (A-Z)", test: (pw) => /[A-Z]/.test(pw) },
  { id: "lower", label: "One lowercase letter (a-z)", test: (pw) => /[a-z]/.test(pw) },
  { id: "digit", label: "One number (0-9)", test: (pw) => /[0-9]/.test(pw) },
  {
    id: "special",
    label: "One special character (e.g. ! @ # $ %)",
    test: (pw) => pw.split("").some((c) => SPECIAL_CHARACTERS.includes(c)),
  },
];

/** Returns the rules the password currently fails. Empty array = acceptable. */
export function checkPassword(password) {
  const pw = password || "";
  return PASSWORD_RULES.filter((rule) => !rule.test(pw));
}

export function isPasswordValid(password) {
  return checkPassword(password).length === 0;
}

/** 0-4, purely for the visual strength bar. */
export function passwordStrength(password) {
  const pw = password || "";
  if (!pw) return 0;
  const met = PASSWORD_RULES.filter((r) => r.test(pw)).length;
  if (met <= 2) return 1;
  if (met === 3) return 2;
  if (met === 4) return 3;
  return pw.length >= 12 ? 4 : 3;
}

export const STRENGTH_LABELS = ["", "Weak", "Fair", "Good", "Strong"];
export const STRENGTH_COLORS = ["#e9ecef", "#dc3545", "#fd7e14", "#0dcaf0", "#198754"];
