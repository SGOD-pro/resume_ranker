import '@testing-library/dom';
import { afterEach, beforeAll, afterAll } from 'vitest';
import { server } from './mocks/server';

// Start MSW server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Reset handlers between tests to prevent state leakage
afterEach(() => server.resetHandlers());

// Clean up after all tests
afterAll(() => server.close());
