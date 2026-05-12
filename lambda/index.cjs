/**
 * Warp contact form Lambda handler
 * Sends form submissions via Resend API
 */

const https = require('https');

const RESEND_API_KEY = process.env.RESEND_API_KEY;
const RESEND_FROM = process.env.RESEND_FROM || 'hello@maiolabs.ai';
const RESEND_TO = process.env.RESEND_TO || 'hello@maiolabs.ai';
const ALLOWED_ORIGIN = process.env.ALLOWED_ORIGIN || '*';

function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

function sendResendEmail(data) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify({
      from: RESEND_FROM,
      to: [RESEND_TO],
      subject: `Warp Contact Form: ${data.email}`,
      html: `
        <h2>New Warp Contact Form Submission</h2>
        <p><strong>Name:</strong> ${escapeHtml(data.name || 'N/A')}</p>
        <p><strong>Email:</strong> ${escapeHtml(data.email)}</p>
        <p><strong>Company:</strong> ${escapeHtml(data.company || 'N/A')}</p>
        <p><strong>Message:</strong></p>
        <p>${escapeHtml(data.message || 'N/A').replace(/\n/g, '<br>')}</p>
        <hr>
        <p><small>Sent from warp.maiolabs.ai</small></p>
      `
    });

    const options = {
      hostname: 'api.resend.com',
      port: 443,
      path: '/emails',
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${RESEND_API_KEY}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve({ success: true, data: JSON.parse(body) });
        } else {
          reject(new Error(`Resend API error: ${res.statusCode} ${body}`));
        }
      });
    });

    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

exports.handler = async (event) => {
  const method = event.requestContext?.http?.method || event.httpMethod;
  const origin = event.headers?.origin || event.headers?.Origin || '';

  // CORS headers
  const corsHeaders = {
    'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
  };

  // OPTIONS preflight
  if (method === 'OPTIONS') {
    return {
      statusCode: 204,
      headers: corsHeaders,
      body: ''
    };
  }

  // GET - info page
  if (method === 'GET') {
    return {
      statusCode: 200,
      headers: {
        ...corsHeaders,
        'Content-Type': 'text/html'
      },
      body: `
        <!DOCTYPE html>
        <html>
        <head><title>Warp Contact Form API</title></head>
        <body style="font-family: system-ui; max-width: 600px; margin: 50px auto; padding: 20px;">
          <h1>Warp Contact Form API</h1>
          <p>POST JSON to this endpoint with: name, email, company (optional), message</p>
          <pre>{"name": "...", "email": "...", "company": "...", "message": "..."}</pre>
        </body>
        </html>
      `
    };
  }

  // POST - handle form submission
  if (method === 'POST') {
    try {
      const body = typeof event.body === 'string' ? JSON.parse(event.body) : event.body;

      if (!body.email || !body.name) {
        return {
          statusCode: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          body: JSON.stringify({ error: 'Missing required fields: name, email' })
        };
      }

      await sendResendEmail(body);

      return {
        statusCode: 200,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ success: true, message: 'Form submitted successfully' })
      };

    } catch (error) {
      console.error('Error:', error);
      return {
        statusCode: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: 'Failed to send email', details: error.message })
      };
    }
  }

  // Method not allowed
  return {
    statusCode: 405,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    body: JSON.stringify({ error: 'Method not allowed' })
  };
};
