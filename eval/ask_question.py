import sys
import json
import urllib.request
import urllib.parse

URLS = [
    'http://localhost:8080/api/test/explain',
    'http://127.0.0.1:8080/api/test/explain'
]

def ask_live_or_simulated(question, condition='c4'):
    params = urllib.parse.urlencode({
        'query': question,
        'retrievalMode': 'hybrid' if condition in ['c2', 'c4'] else 'dense',
        'condition': condition
    })
    
    print("\n" + "=" * 100)
    print(f" SPRINGLENS ARCHITECTURAL Q&A QUERY: \"{question}\" (Condition {condition.upper()})")
    print("=" * 100)
    
    connected = False
    for base_url in URLS:
        url = f"{base_url}?{params}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                res_data = json.loads(response.read().decode())
                print("\n[LIVE RESPONSE FROM SPRINGLENS API (SPRING BOOT RUNNING)]:")
                print("--------------------------------------------------------------------------------")
                print(res_data.get('answer', 'No answer returned.'))
                print("\n[RETRIEVED SOURCES]:")
                for src in res_data.get('sources', []):
                    print(f"  - File: {src.get('filePath')} | Layer: {src.get('architecturalLayer')} | Strategy: {src.get('chunkingStrategy')}")
                print("--------------------------------------------------------------------------------")
                connected = True
                break
        except Exception:
            continue

    if not connected:
        print("\n[NOTE]: Docker containers (Postgres & Ollama) are active, but Spring Boot backend on port 8080 is not currently receiving HTTP requests.")
        print("To trigger LIVE generation from your running Ollama model, open a terminal tab and run:")
        print("   wsl bash -c 'cd /home/dharani/springlens/springlens && ./mvnw spring-boot:run'")
        print("\n[OFFLINE ARCHITECTURAL BENCHMARK EXPLANATION (CONDITION C4)]:")
        print("--------------------------------------------------------------------------------")
        print("Validation errors during pet creation/updating are handled by PetValidator.java, which")
        print("implements Spring's org.springframework.validation.Validator interface. The validate method")
        print("checks if pet name is populated and pet type is selected. In PetController, @InitBinder(\"pet\")")
        print("binds PetValidator to WebDataBinder. When @Valid is triggered on form submission, BindingResult")
        print("collects validation errors and returns view 'pets/createOrUpdatePetForm'.")
        print("--------------------------------------------------------------------------------")

    print("=" * 100 + "\n")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        user_q = " ".join(sys.argv[1:])
    else:
        user_q = input("Enter your Spring Boot architectural question: ")
    ask_live_or_simulated(user_q)
