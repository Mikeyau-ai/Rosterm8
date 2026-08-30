/**
 * Build-time configuration.
 *
 * There is no build step, so this file is the one place to edit by hand.
 */

/**
 * Base URL of the sync worker, with no trailing slash.
 *
 * Leave it empty and sync is simply switched off - the app works exactly as it
 * always has, entirely on the device. Set it to your deployed Cloudflare Worker
 * (see worker/README.md) and the Sync section appears in Settings.
 *
 * Example: 'https://rosterm8-sync.your-name.workers.dev'
 */
export const SYNC_URL = 'https://rosterm8-sync.mikey-257.workers.dev';
