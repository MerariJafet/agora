const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try {
    const page = await browser.newPage();
    const errors = [];
    let callbackCalls = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.routeWebSocket('**/agora-api/v1/realtime/web', ws => ws.onMessage(() => {}));
    await page.route('**/agora-api/**', async route => {
      const path = new URL(route.request().url()).pathname;
      let body;
      if (path.endsWith('/auth/oidc/start')) body = {authorization_url:'https://identity.example/authorize?state=browser-test',state:'browser-test'};
      else if (path.endsWith('/auth/oidc/callback')) {
        callbackCalls++;
        assert.deepEqual(route.request().postDataJSON(),{code:'test-code',state:'browser-test'});
        body = {user_id:'test-user',username:'TEST_NOT_REAL',csrf_token:'test-only'};
      } else if (path.endsWith('/auth/me')) body = {user_id:'test-user',username:'TEST_NOT_REAL',csrf_token:'test-only'};
      else if (path.endsWith('/owner/agents')) body = {agents:[]};
      else if (path.endsWith('/world/manifest')) body = {
        world_version:'1.0.0',name:'TEST_NOT_REAL isolated world',bounds:{min_x:-1300,min_y:-900,max_x:1300,max_y:1300},
        landmarks:[{id:'central',name:'TEST_NOT_REAL Plaza',state:'ACTIVE',space_id:'test-plaza',purpose:'UI fixture',shape:'district',x:0,y:0,radius:260}],
        portals:[],nav_edges:[],lod:{mid_zoom_below:0.45,far_zoom_below:0.22,cluster_population_above:150}
      };
      else if (path.endsWith('/world/population')) body = {spaces:{},total_present:0};
      else return route.fulfill({status:503,contentType:'application/json',body:'{"error":"ISOLATED_TEST_NO_API"}'});
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    await page.route('https://identity.example/**', route => route.fulfill({status:200,contentType:'text/html',body:'TEST_NOT_REAL mock issuer'}));
    const response = await page.goto('http://127.0.0.1:3099/login');
    const csp = response.headers()['content-security-policy'];
    assert.ok(csp.includes("object-src 'none'"));
    assert.ok(!csp.includes('unsafe-eval'));
    assert.equal(await page.getByPlaceholder('your username').count(),0);
    await page.getByRole('button',{name:'Sign in with identity provider'}).click();
    await page.waitForURL('https://identity.example/**');
    console.log('PASS production login hides dev form; OIDC start redirects to HTTPS issuer');
    await page.goto('http://127.0.0.1:3099/login/callback?code=test-code&state=browser-test');
    await page.waitForURL('**/my-agents');
    assert.equal(callbackCalls,1);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('agora.oidc.state')),null);
    console.log('PASS browser-bound state callback exchanged once; navigation to my-agents; state removed');
    await page.goto('http://127.0.0.1:3099/login/callback?code=attacker-code&state=wrong');
    await page.getByText('Sign-in expired or did not originate in this browser tab. Please start again.').waitFor();
    assert.equal(callbackCalls,1);
    assert.ok(!page.url().includes('?'));
    console.log('PASS invalid callback rejected before API request; URL credentials removed');
    assert.deepEqual(errors,[]);
    console.log('PASS no browser runtime errors; production CSP excludes eval');
    await page.screenshot({path:__dirname+'/web-login-callback.png',fullPage:true});
    await page.goto('http://127.0.0.1:3099/world');
    await page.locator('canvas').waitFor({state:'visible',timeout:10000}).catch(async error => { console.error((await page.locator('body').innerText()).slice(0,6000), errors); throw error; });
    assert.equal(await page.getByText('Graphics unavailable',{exact:true}).count(),0);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:__dirname+'/web-world-mock.png',fullPage:true});
    console.log('PASS Pixi world renders visible canvas under production CSP with isolated fixture and mocked websocket');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
