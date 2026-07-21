# Ambiente LayoutLMv3 + BiLSTM

La pipeline multimodale è stata verificata nel seguente ambiente:

- Python: 3.12.11
- PyTorch: 2.7.1+cu118
- Transformers: 5.13.1
- Pillow: 12.2.0
- NumPy: 2.4.4
- CUDA runtime: 11.8
- GPU disponibile: sì

## Installazione

Le dipendenze Python generali sono elencate nel file `requirements.txt`.

L'installazione di PyTorch può variare a seconda dell'ambiente:

- CPU;
- macOS;
- GPU NVIDIA;
- versione CUDA disponibile.

Per questo motivo, il file `requirements.txt` dichiara `torch` senza imporre
una specifica build CUDA.

L'ambiente sopra riportato è quello nel quale sono stati eseguiti con successo:

1. il caricamento del checkpoint multiclasse;
2. la lettura di immagini JPEG;
3. la predizione su 123 pagine del Senato, `regno_02`;
4. la classificazione di 3.395 blocchi senza predizioni mancanti.
