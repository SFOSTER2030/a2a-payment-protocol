/* ------------------------------------------------------------------ */
/*  Pulse Payments A2A SDK - Webhook Signature Verification           */
/* ------------------------------------------------------------------ */

import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * Verify the HMAC-SHA256 signature attached to an incoming webhook.
 *
 * The Pulse API signs every outgoing webhook request using the shared
 * secret configured in your dashboard.  The signature is delivered in
 * the `X-Pulse-Signature` header as a hex-encoded HMAC-SHA256 digest.
 *
 * An optional `tolerance` (in seconds) rejects payloads whose
 * `X-Pulse-Timestamp` header is too far in the past, guarding against
 * replay attacks.
 *
 * @param payload   - The raw request body (Buffer or string, **not** parsed JSON).
 * @param signature - Value of the `X-Pulse-Signature` header.
 * @param secret    - Your webhook signing secret.
 * @param options   - Optional settings.
 * @param options.timestamp - Value of the `X-Pulse-Timestamp` header (unix seconds).
 * @param options.tolerance - Maximum age of the timestamp in seconds (default 300 = 5 min).
 * @returns `true` when the signature is valid.
 * @throws  {Error} if the signature is invalid or the timestamp is outside the tolerance window.
 */
export function verifyWebhookSignature(
  payload: string | Buffer,
  signature: string,
  secret: string,
  options?: { timestamp?: string | number; tolerance?: number },
): boolean {
  if (!payload || !signature || !secret) {
    throw new Error("payload, signature, and secret are all required");
  }

  // ---- Timestamp / replay protection --------------------------------
  if (options?.timestamp !== undefined) {
    const ts =
      typeof options.timestamp === "string"
        ? parseInt(options.timestamp, 10)
        : options.timestamp;

    if (Number.isNaN(ts)) {
      throw new Error("Invalid timestamp value");
    }

    const tolerance = options.tolerance ?? 300; // default 5 minutes
    const now = Math.floor(Date.now() / 1000);

    if (Math.abs(now - ts) > tolerance) {
      throw new Error(
        `Webhook timestamp is outside the tolerance window (${tolerance}s)`,
      );
    }
  }

  // ---- HMAC verification --------------------------------------------
  const expected = createHmac("sha256", secret)
    .update(typeof payload === "string" ? payload : payload)
    .digest("hex");

  const sigBuffer = Buffer.from(signature, "hex");
  const expectedBuffer = Buffer.from(expected, "hex");

  if (sigBuffer.length !== expectedBuffer.length) {
    throw new Error("Webhook signature verification failed");
  }

  if (!timingSafeEqual(sigBuffer, expectedBuffer)) {
    throw new Error("Webhook signature verification failed");
  }

  return true;
}
