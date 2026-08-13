import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  page.on('console', msg => console.log('BROWSER:', msg.text()));

  console.log('Navigating to test page...');
  await page.goto('http://localhost:5173/test/e2e.html');

  console.log('Clicking run tests...');
  await page.evaluate(() => {
    window.runTests();
  });

  console.log('Waiting for tests to finish... This may take a few minutes as it processes 5 JDs x 20 resumes.');
  
  // Wait until the status is no longer 'running' or 'info'
  await page.waitForFunction(() => {
    const statusEl = document.getElementById('status');
    if (!statusEl) return false;
    const text = statusEl.textContent;
    return text.includes('PASSED') || text.includes('FAILED') || text.includes('CRASH');
  }, { timeout: 600000 }); // 10 minutes timeout

  const logText = await page.evaluate(() => {
    const logEl = document.getElementById('log');
    return logEl ? logEl.innerText : 'No log found';
  });

  const statusText = await page.evaluate(() => {
    const statusEl = document.getElementById('status');
    return statusEl ? statusEl.innerText : 'No status found';
  });

  console.log('\n================== E2E REPORT ==================\n');
  console.log('STATUS:', statusText);
  console.log('\n==================== LOGS ====================\n');
  console.log(logText);
  
  await browser.close();
})();
