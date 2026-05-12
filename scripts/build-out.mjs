#!/usr/bin/env node
/**
 * Build script for Warp website
 * Reads website/index.html and injects Lambda Function URL
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = dirname(__dirname);

const REGISTER_FUNCTION_URL = process.env.REGISTER_FUNCTION_URL || '__WARP_LAMBDA_ENDPOINT__';
const SOURCE_HTML = `${PROJECT_ROOT}/website/index.html`;
const OUTPUT_HTML = `${PROJECT_ROOT}/out/index.html`;

console.log('📦 Building Warp website...');
console.log(`   Source: ${SOURCE_HTML}`);
console.log(`   Output: ${OUTPUT_HTML}`);
console.log(`   Lambda URL: ${REGISTER_FUNCTION_URL.startsWith('__WARP_') ? '[not configured]' : REGISTER_FUNCTION_URL}`);

try {
  // Create out directory
  mkdirSync(`${PROJECT_ROOT}/out`, { recursive: true });

  // Read source HTML
  let html = readFileSync(SOURCE_HTML, 'utf-8');

  // Replace placeholder (currently no form, but ready for future)
  html = html.replace(/__WARP_LAMBDA_ENDPOINT__/g, REGISTER_FUNCTION_URL);

  // Write output
  writeFileSync(OUTPUT_HTML, html, 'utf-8');

  console.log('✅ Build complete!');
} catch (error) {
  console.error('❌ Build failed:', error.message);
  process.exit(1);
}
