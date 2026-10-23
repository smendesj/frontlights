# Test-driven development

Read when: an implementer's brief names it, before the first test of a slice; the coordinator reads it before a
hotfix of the free test.

TDD is the red → green loop, the default practice of every slice and never a gate (`references/development.md`,
"Which tests run when"; a run "só com teste assistido" skips it). This reference makes that loop produce tests worth
keeping: what a good test is, where tests go, what to mock, the anti-patterns, the rules of the loop and what to do
when a red surprises you. Every section applies on every cycle: consult them before and during the loop, not after.

When exploring the codebase, read `CONTEXT.md` (if it exists) so test names and interface vocabulary match the
project's domain language, and respect ADRs in the area you're touching.

Follow the conventions recorded in the issue's `## Decisões de implementação` (`## Abordagem e convenções` in issues
published before this section existed, `## Approach and conventions` before 0.28.1) and in the discovery log:
structure, naming, error handling, libraries and test style of the surrounding code. Break a convention only where
that section names the approved break. Finding mid-work that the pattern is concretely worse, or that the approved
approach does not fit, stops the slice and returns the question to the coordinator; never switch approach or pattern
silently.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests
shouldn't. A good test reads like a specification: "user can checkout with valid cart" tells you exactly what
capability exists, and it survives refactors because it doesn't care about internal structure.

```typescript
// GOOD: Tests observable behavior
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});

// BAD: Tests implementation details
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

A good test tests behavior users or callers care about, uses the public API only, survives internal refactors,
describes WHAT, not HOW, and makes one logical assertion. Red flags: mocking internal collaborators, testing private
methods, asserting on call counts or order, a test that breaks when refactoring without behavior change, a name that
describes HOW, verifying through external means instead of the interface:

```typescript
// BAD: Bypasses interface to verify
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: Verifies through interface
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

## Seams: where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside.
Tests live at seams, never against internals.

**Test only at pre-agreed seams.** The seams under test are part of each issue (`## Decisões de teste` in
`templates/issue.md`, `## Seams sob teste` or `## Seams under test` in older issues, and the `Seams:` under each box)
and were approved when the issues were published. You can't test everything; agreeing the seams up front is how
testing effort lands on the critical paths and complex logic instead of every edge case. Before the first test,
restate the slice's seams in your report. No test is written at an unconfirmed seam. If the issue lists none, a
listed seam does not exist or cannot observe the acceptance behavior, or the shape of the interface is itself in
question (how deep the module is, where the seam belongs, what it should expose), stop and return the question
"What's the public interface, and which seams should we test?" to the coordinator.

## When to mock

Mock at **system boundaries** only: external APIs (payment, email), databases (sometimes; prefer a test database),
time and randomness, the file system (sometimes). Don't mock your own classes or modules, internal collaborators, or
anything you control. At a boundary, design interfaces that are easy to mock: pass the external dependency in (dependency
injection) rather than creating it inside, and prefer one function per external operation over one generic fetcher,
so each mock returns one shape, the setup has no conditional logic, and the test shows which endpoints it exercises.

```typescript
// Easy to mock
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to mock
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

## Anti-patterns

- **Implementation-coupled**: mocks internal collaborators, tests private methods, or verifies through a side channel
  (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior
  hasn't changed.
- **Tautological**: the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a +
  b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and
  can never disagree with the code. Expected values must come from an independent source of truth: a known-good
  literal, a worked example, the spec (`expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15)`).
- **Horizontal slicing**: writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior:
  you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you
  commit to test structure before understanding the implementation. Work in **vertical slices** instead: one test →
  one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Rules of the loop

- **Red before green.** Write the failing test first, run it and capture the actual expected failure, then write only
  enough code to pass it and rerun the focused tests. Don't anticipate future tests or add speculative features.
- **The red must be behavioral.** An import error or broken harness is not the intended red. Fix the harness and
  obtain a meaningful failing assertion.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle, each tied to one acceptance
  behavior.
- **Refactoring is not part of the loop.** It comes after it, without changing behavior or adding tests at new seams.
- **Evidence is real.** Preserve commands, exit codes, counts and output paths. Never invent failure evidence for a
  nontestable documentation change; state the exception and verify the relevant behavior another way.

## Diagnosing an unexpected red

A test that fails where you expected green, or fails differently from the red you wrote, is a fact to reproduce before
it is a bug to fix. Reproduce the red before the hypothesis:

1. Rerun only that test, alone, and capture the exact failure: the assertion, the values, the traceback line.
2. Run it on the commit before your change (`git stash` or the base of the slice). Red there too means the cause is not
   your change: report it with both runs instead of fixing around it.
3. Read the line the traceback names and the input it got; write down one hypothesis that explains the exact values.
4. Prove the hypothesis with the smallest check (a print, a narrower test, one changed input) before editing code.
5. Fix, rerun the focused test, then the slice's tests. A fix that turns it green without explaining the old values is
   not a diagnosis: say so in the report.

A flaky red (green on rerun) is reported as flaky with both runs, never retried until green.
