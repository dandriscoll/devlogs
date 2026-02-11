/**
 * Time-based circuit breaker with auto-recovery.
 *
 * Port of the Go SDK circuit breaker pattern:
 * - Opens on failure, pauses indexing for `duration` (default 60s)
 * - Auto-resets after duration expires (time-based)
 * - Closes immediately on explicit success (RecordSuccess)
 * - Throttles error output to once per `errorInterval` (default 10s)
 */
export class CircuitBreaker {
  private isOpen = false;
  private openUntil = 0;
  private lastErrorPrinted = 0;
  private readonly duration: number;
  private readonly errorInterval: number;
  private readonly stderr: (msg: string) => void;

  /**
   * @param duration - How long to keep circuit open in ms (default: 60000)
   * @param errorInterval - Min interval between error prints in ms (default: 10000)
   * @param stderr - Output function for error messages (default: process.stderr.write)
   */
  constructor(
    duration = 60_000,
    errorInterval = 10_000,
    stderr?: (msg: string) => void
  ) {
    this.duration = duration;
    this.errorInterval = errorInterval;
    this.stderr = stderr ?? ((msg: string) => process.stderr.write(msg + '\n'));
  }

  /**
   * Check if the circuit breaker is open (should skip indexing).
   * Auto-resets if duration has expired.
   */
  shouldSkip(): boolean {
    if (!this.isOpen) return false;
    if (Date.now() >= this.openUntil) {
      this.isOpen = false;
      return false;
    }
    return true;
  }

  /**
   * Record a failure - opens the circuit breaker.
   */
  recordFailure(err: unknown): void {
    const now = Date.now();
    this.isOpen = true;
    this.openUntil = now + this.duration;

    // Throttle error printing
    if (now - this.lastErrorPrinted > this.errorInterval) {
      this.lastErrorPrinted = now;
      const secs = Math.round(this.duration / 1000);
      this.stderr(
        `[devlogs] Failed to index log, pausing indexing for ${secs}s: ${err}`
      );
    }
  }

  /**
   * Record a success - closes the circuit breaker.
   */
  recordSuccess(): void {
    if (this.isOpen) {
      this.isOpen = false;
      this.stderr('[devlogs] Connection restored, resuming indexing');
    }
  }
}
