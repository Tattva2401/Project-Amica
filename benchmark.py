import json
import urllib.request
import urllib.error
import time
import subprocess
import os

OLLAMA_URL = "http://localhost:11434"
MODEL = "dolphin-llama3:latest"
CONTEXT_SIZES = [2048, 3072, 4096, 6144, 8192]
PROMPT = (
    "You are an AI companion named Amica. You are helpful, friendly, and deeply knowledgeable. "
    "Respond to the user's inquiry with enthusiasm and in-character detail. "
    "The user has just asked you about your capabilities and how you process information. "
    "Please provide a comprehensive explanation of your thought process, your underlying architecture, "
    "and how you can assist the user in their daily tasks. Make sure to emphasize your unique personality "
    "and the fact that you are running locally on their machine, ensuring complete privacy and security. "
    "Keep your response detailed and engaging, showcasing your full potential as a personalized AI assistant. "
    "Let's see what you can do! " + " ".join(["padding"] * 80) # Ensure it's long enough (>= 150 words)
)

def check_ollama():
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            models = [m['name'] for m in data.get('models', [])]
            if MODEL not in models:
                print(f"Warning: {MODEL} not found in Ollama. Available models: {models}")
                for m in models:
                    if 'llama3' in m or 'dolphin' in m:
                        return m
                if models:
                    return models[0]
                else:
                    print("No models found in Ollama. Please pull a model.")
                    exit(1)
            return MODEL
    except urllib.error.URLError as e:
        print(f"Error connecting to Ollama: {e}")
        print("Please ensure Ollama is running at http://localhost:11434")
        exit(1)

def get_swap_usage():
    try:
        output = subprocess.check_output(["sysctl", "vm.swapusage"], text=True).strip()
        # Output: vm.swapusage: total = 1024.00M  used = 730.00M  free = 294.00M  (encrypted)
        parts = output.split()
        for i, part in enumerate(parts):
            if part == "used":
                return parts[i+2] # E.g. '730.00M'
        return output
    except Exception:
        return "N/A"

def get_ollama_ps():
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/ps")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            models = data.get('models', [])
            if models:
                size = models[0].get('size_vram', models[0].get('size', 0))
                return f"{size / (1024**3):.2f} GB"
            return "N/A"
    except Exception:
        return "N/A"

def run_benchmark(model, ctx_size):
    print(f"\n--- Testing Context Size: {ctx_size} ---")
    swap_before = get_swap_usage()
    
    payload = {
        "model": model,
        "prompt": PROMPT,
        "stream": False,
        "options": {
            "num_ctx": ctx_size,
            "num_predict": 256
        }
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=data, headers={'Content-Type': 'application/json'})
    
    start_time = time.time()
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error during generation: {e}")
        return None
    
    end_time = time.time()
    wall_clock = end_time - start_time
    
    swap_after = get_swap_usage()
    ollama_mem = get_ollama_ps()
    
    load_duration = result.get('load_duration', 0) / 1e9
    prompt_eval_count = result.get('prompt_eval_count', 0)
    prompt_eval_duration = result.get('prompt_eval_duration', 0) / 1e9
    eval_count = result.get('eval_count', 0)
    eval_duration = result.get('eval_duration', 0) / 1e9
    
    prompt_tps = prompt_eval_count / prompt_eval_duration if prompt_eval_duration > 0 else 0
    gen_tps = eval_count / eval_duration if eval_duration > 0 else 0
    
    print(f"Wall Clock: {wall_clock:.2f}s | Load: {load_duration:.2f}s")
    print(f"Prompt TPS: {prompt_tps:.2f} | Gen TPS: {gen_tps:.2f}")
    print(f"Ollama Active Mem: {ollama_mem}")
    print(f"Swap: {swap_before} -> {swap_after}")
    
    return {
        "ctx_size": ctx_size,
        "wall_clock_s": wall_clock,
        "load_duration_s": load_duration,
        "prompt_tps": prompt_tps,
        "gen_tps": gen_tps,
        "ollama_mem": ollama_mem,
        "swap_before": swap_before,
        "swap_after": swap_after,
        "eval_count": eval_count
    }

def main():
    print("Starting Project Amica Benchmark (v0.0)...")
    target_model = check_ollama()
    print(f"Targeting model: {target_model}")
    
    print("Pre-warming model (running a quick generation request)...")
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=json.dumps({"model": target_model, "prompt": "hi", "stream": False}).encode('utf-8'), headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Pre-warm failed, moving on: {e}")

    results = []
    for ctx in CONTEXT_SIZES:
        res = run_benchmark(target_model, ctx)
        if res:
            results.append(res)
        print("Cooling down for 3 seconds...")
        time.sleep(3)
        
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=4)
        
    print("\n" + "="*85)
    print("BENCHMARK SUMMARY")
    print("="*85)
    print(f"{'Ctx Size':<10} | {'Wall (s)':<10} | {'Prompt TPS':<12} | {'Gen TPS':<10} | {'Ollama Mem':<12} | {'Swap (end)':<10}")
    print("-" * 85)
    for r in results:
        print(f"{r['ctx_size']:<10} | {r['wall_clock_s']:<10.2f} | {r['prompt_tps']:<12.2f} | {r['gen_tps']:<10.2f} | {r['ollama_mem']:<12} | {r['swap_after']:<10}")
    
    print("\nRECOMMENDATION:")
    
    optimal_ctx = results[0]['ctx_size']
    max_ctx = results[-1]['ctx_size']
    
    # Simple heuristics to find hard ceiling and optimal context
    for i in range(1, len(results)):
        tps_drop = results[i-1]['gen_tps'] - results[i]['gen_tps']
        if tps_drop > (results[i-1]['gen_tps'] * 0.25): # 25% drop indicates memory thrashing ceiling
            max_ctx = results[i-1]['ctx_size']
            break
            
    best_tps = 0
    for r in results:
        if r['gen_tps'] > best_tps and r['ctx_size'] <= max_ctx:
            best_tps = r['gen_tps']
            optimal_ctx = r['ctx_size']
            
    print(f"- Optimal starting context window: {optimal_ctx}")
    print(f"- Hard ceiling context window before thrashing: {max_ctx}")
    print("="*85)

if __name__ == '__main__':
    main()
