"""UI Bridge for Federated Mode.

This module provides helpers for custom agent UIs to communicate with the
DE platform shell via postMessage.

Usage in Python:
    from platform_sdk import get_ui_bridge_script, generate_ui_bridge_html
    
    # Get the JavaScript to include in your custom UI
    script = get_ui_bridge_script()
    
    # Or generate a full HTML snippet
    html = generate_ui_bridge_html()

Usage in JavaScript (the generated script):
    // Initialize the bridge
    const bridge = new DEBridge();
    
    // Run the agent
    const result = await bridge.run({ instructions: "Hello" });
    
    // Invoke a specific tool
    const toolResult = await bridge.invokeTool("myTool", { arg1: "value" });
"""

import json
from typing import Optional


# The JavaScript bridge code that custom UIs should include
DE_BRIDGE_JS = '''
/**
 * DE Platform Bridge - Enables communication between custom agent UIs and the DE shell.
 * 
 * This script should be included in any custom UI that runs inside the DE platform's iframe.
 * It provides methods to:
 * - Run the agent through the platform's governed endpoint
 * - Invoke specific tools
 * - Access user context from the host shell
 * 
 * Usage:
 *   const bridge = new DEBridge();
 *   
 *   // Wait for connection to host
 *   await bridge.ready();
 *   
 *   // Get user context
 *   const user = bridge.getUser();
 *   
 *   // Run agent
 *   const result = await bridge.run({ instructions: "Process this data" });
 *   
 *   // Invoke a tool
 *   const toolResult = await bridge.invokeTool("transform", { data: "hello" });
 */
class DEBridge {
  constructor() {
    this._hostOrigin = null;
    this._agentId = null;
    this._user = null;
    this._schema = null;
    this._pendingRequests = new Map();
    this._requestCounter = 0;
    this._isReady = false;
    this._readyPromise = null;
    this._readyResolve = null;
    
    // Parse URL params for initial context
    this._parseUrlParams();
    
    // Set up message listener
    window.addEventListener('message', this._handleMessage.bind(this));
    
    // Create ready promise
    this._readyPromise = new Promise((resolve) => {
      this._readyResolve = resolve;
    });
    
    // Announce ourselves to the host
    this._sendToHost({ type: 'DE_READY' });
  }
  
  _parseUrlParams() {
    const params = new URLSearchParams(window.location.search);
    
    // Decode auth from URL params
    const authParam = params.get('de_auth');
    if (authParam) {
      try {
        this._user = JSON.parse(atob(authParam));
      } catch (e) {
        console.warn('[DEBridge] Failed to parse auth param:', e);
      }
    }
    
    this._agentId = params.get('agent_id');
    this._hostOrigin = params.get('host_origin') || '*';
  }
  
  _handleMessage(event) {
    // Validate origin if we know the host
    if (this._hostOrigin && this._hostOrigin !== '*') {
      if (event.origin !== this._hostOrigin) {
        return;
      }
    }
    
    const { type, payload, requestId, success, error } = event.data || {};
    
    switch (type) {
      case 'DE_CONTEXT':
        // Host is sending us context
        this._agentId = payload?.agentId || this._agentId;
        this._user = payload?.user || this._user;
        this._schema = payload?.schema;
        this._hostOrigin = event.origin;
        this._isReady = true;
        if (this._readyResolve) {
          this._readyResolve();
        }
        break;
        
      case 'DE_RUN_RESPONSE':
      case 'DE_TOOL_RESPONSE':
        // Response to a request we made
        const pending = this._pendingRequests.get(requestId);
        if (pending) {
          this._pendingRequests.delete(requestId);
          if (success) {
            pending.resolve(payload);
          } else {
            pending.reject(new Error(error || 'Request failed'));
          }
        }
        break;
    }
  }
  
  _sendToHost(message) {
    if (window.parent && window.parent !== window) {
      const targetOrigin = this._hostOrigin || '*';
      window.parent.postMessage(message, targetOrigin);
    } else {
      console.warn('[DEBridge] Not running in iframe, cannot send to host');
    }
  }
  
  _makeRequest(type, payload) {
    return new Promise((resolve, reject) => {
      const requestId = `req_${++this._requestCounter}_${Date.now()}`;
      
      this._pendingRequests.set(requestId, { resolve, reject });
      
      this._sendToHost({
        type,
        requestId,
        payload,
      });
      
      // Timeout after 2 minutes
      setTimeout(() => {
        if (this._pendingRequests.has(requestId)) {
          this._pendingRequests.delete(requestId);
          reject(new Error('Request timeout'));
        }
      }, 120000);
    });
  }
  
  /**
   * Wait for the bridge to be ready (connected to host).
   * @returns {Promise<void>}
   */
  async ready() {
    if (this._isReady) return;
    return this._readyPromise;
  }
  
  /**
   * Check if the bridge is connected to the host.
   * @returns {boolean}
   */
  isReady() {
    return this._isReady;
  }
  
  /**
   * Get the current user context.
   * @returns {Object|null}
   */
  getUser() {
    return this._user;
  }
  
  /**
   * Get the agent ID.
   * @returns {string|null}
   */
  getAgentId() {
    return this._agentId;
  }
  
  /**
   * Get the agent schema (if provided by host).
   * @returns {Object|null}
   */
  getSchema() {
    return this._schema;
  }
  
  /**
   * Run the agent through the DE platform.
   * @param {Object} payload - Run parameters (instructions, model, etc.)
   * @returns {Promise<Object>} - Run result
   */
  async run(payload) {
    return this._makeRequest('DE_RUN_REQUEST', payload);
  }
  
  /**
   * Invoke a specific tool through the DE platform.
   * @param {string} toolName - Name of the tool to invoke
   * @param {Object} args - Tool arguments
   * @returns {Promise<Object>} - Tool result
   */
  async invokeTool(toolName, args) {
    return this._makeRequest('DE_TOOL_INVOKE', {
      toolName,
      arguments: args,
    });
  }
  
  /**
   * Log an event to the console (for debugging).
   * @param {string} message - Log message
   * @param {Object} data - Optional data to log
   */
  log(message, data = null) {
    console.log(`[DEBridge] ${message}`, data || '');
  }
}

// Auto-initialize and expose globally
window.DEBridge = DEBridge;
window.deBridge = new DEBridge();
'''


def get_ui_bridge_script() -> str:
    """Get the JavaScript bridge code to include in custom UIs.
    
    Returns:
        str: JavaScript code for the DEBridge class
    """
    return DE_BRIDGE_JS


def generate_ui_bridge_html(
    include_styles: bool = True,
    auto_init: bool = True,
) -> str:
    """Generate an HTML snippet with the bridge script.
    
    Args:
        include_styles: Whether to include basic loading styles
        auto_init: Whether to auto-initialize the bridge
        
    Returns:
        str: HTML snippet to include in custom UIs
    """
    styles = ""
    if include_styles:
        styles = '''
<style>
  .de-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    font-family: system-ui, sans-serif;
    color: #666;
  }
  .de-loading::after {
    content: "Connecting to DE Platform...";
  }
  .de-ready .de-loading {
    display: none;
  }
</style>
'''
    
    init_script = ""
    if auto_init:
        init_script = '''
<script>
  // Wait for bridge to be ready
  document.addEventListener('DOMContentLoaded', async () => {
    await window.deBridge.ready();
    document.body.classList.add('de-ready');
    console.log('[DEBridge] Connected to host:', {
      agentId: window.deBridge.getAgentId(),
      user: window.deBridge.getUser(),
    });
  });
</script>
'''
    
    return f'''
<!-- DE Platform Bridge -->
{styles}
<script>
{DE_BRIDGE_JS}
</script>
{init_script}
'''


def generate_vue_composable() -> str:
    """Generate a Vue 3 composable for the bridge.
    
    Returns:
        str: Vue composable code (useDEBridge)
    """
    return '''
// useDEBridge.js - Vue 3 composable for DE Platform Bridge
import { ref, onMounted, onUnmounted } from 'vue';

export function useDEBridge() {
  const isReady = ref(false);
  const user = ref(null);
  const agentId = ref(null);
  const schema = ref(null);
  const loading = ref(false);
  const error = ref(null);
  
  let bridge = null;
  
  onMounted(async () => {
    // Get global bridge instance
    bridge = window.deBridge;
    
    if (bridge) {
      await bridge.ready();
      isReady.value = true;
      user.value = bridge.getUser();
      agentId.value = bridge.getAgentId();
      schema.value = bridge.getSchema();
    }
  });
  
  async function run(payload) {
    if (!bridge) throw new Error('Bridge not initialized');
    
    loading.value = true;
    error.value = null;
    
    try {
      const result = await bridge.run(payload);
      return result;
    } catch (e) {
      error.value = e.message;
      throw e;
    } finally {
      loading.value = false;
    }
  }
  
  async function invokeTool(toolName, args) {
    if (!bridge) throw new Error('Bridge not initialized');
    
    loading.value = true;
    error.value = null;
    
    try {
      const result = await bridge.invokeTool(toolName, args);
      return result;
    } catch (e) {
      error.value = e.message;
      throw e;
    } finally {
      loading.value = false;
    }
  }
  
  return {
    isReady,
    user,
    agentId,
    schema,
    loading,
    error,
    run,
    invokeTool,
  };
}
'''


def generate_react_hook() -> str:
    """Generate a React hook for the bridge.
    
    Returns:
        str: React hook code (useDEBridge)
    """
    return '''
// useDEBridge.js - React hook for DE Platform Bridge
import { useState, useEffect, useCallback } from 'react';

export function useDEBridge() {
  const [isReady, setIsReady] = useState(false);
  const [user, setUser] = useState(null);
  const [agentId, setAgentId] = useState(null);
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  useEffect(() => {
    const bridge = window.deBridge;
    
    if (bridge) {
      bridge.ready().then(() => {
        setIsReady(true);
        setUser(bridge.getUser());
        setAgentId(bridge.getAgentId());
        setSchema(bridge.getSchema());
      });
    }
  }, []);
  
  const run = useCallback(async (payload) => {
    const bridge = window.deBridge;
    if (!bridge) throw new Error('Bridge not initialized');
    
    setLoading(true);
    setError(null);
    
    try {
      const result = await bridge.run(payload);
      return result;
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);
  
  const invokeTool = useCallback(async (toolName, args) => {
    const bridge = window.deBridge;
    if (!bridge) throw new Error('Bridge not initialized');
    
    setLoading(true);
    setError(null);
    
    try {
      const result = await bridge.invokeTool(toolName, args);
      return result;
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);
  
  return {
    isReady,
    user,
    agentId,
    schema,
    loading,
    error,
    run,
    invokeTool,
  };
}
'''


def save_bridge_assets(output_dir: str) -> None:
    """Save all bridge assets to a directory.
    
    Args:
        output_dir: Directory to save assets to
        
    Creates:
        - de-bridge.js: The core JavaScript bridge
        - useDEBridge.vue.js: Vue 3 composable
        - useDEBridge.react.js: React hook
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'de-bridge.js'), 'w') as f:
        f.write(get_ui_bridge_script())
    
    with open(os.path.join(output_dir, 'useDEBridge.vue.js'), 'w') as f:
        f.write(generate_vue_composable())
    
    with open(os.path.join(output_dir, 'useDEBridge.react.js'), 'w') as f:
        f.write(generate_react_hook())
    
    print(f"✅ Bridge assets saved to {output_dir}/")
    print("  - de-bridge.js")
    print("  - useDEBridge.vue.js")
    print("  - useDEBridge.react.js")
