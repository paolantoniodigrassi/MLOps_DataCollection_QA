#!/bin/bash
# run_pipeline.sh - Entry point CLI per la pipeline unificata
# Estrazione DICOM + Quality Assurance

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Directory di default
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_OUTPUT_DIR="${SCRIPT_DIR}/output"
DEFAULT_DATA_DIR="${SCRIPT_DIR}/data"

echo ""
echo -e "${BOLD}${CYAN}   UNIFIED PIPELINE: DICOM Extraction + Quality Assurance ${NC}"
echo ""

# Scelta modalità
while true; do
    echo -e "${BOLD}Select the execution mode:${NC}"
    echo ""
    echo -e "  ${GREEN}1)${NC} Extract from PACS (from CSV file with patient names) + perform QA"
    echo -e "  ${GREEN}2)${NC} Perform QA on DICOM files already present locally"
    echo ""
    read -p "Choice [1/2]: " MODE_CHOICE

    case "$MODE_CHOICE" in
        1) PIPELINE_MODE="csv"; break ;;
        2) PIPELINE_MODE="local"; break ;;
        *)
            echo -e "${RED}[ERROR] Invalid choice. Please try again.${NC}"
            echo ""
            ;;
    esac
done

# Modalità CSV

if [ "$PIPELINE_MODE" == "csv" ]; then
    echo ""
    echo -e "${BOLD}${CYAN} Mode: Extract from PACS + QA${NC}"
    echo ""

    # Cerca CSV nella cartella input_csv
    CSV_COUNT=$(find "${SCRIPT_DIR}/input_csv" -maxdepth 1 -name "*.csv" | wc -l)

    if [ "$CSV_COUNT" -eq 0 ]; then
        echo -e "${RED}[ERROR] No CSV file found in input_csv/${NC}"
        exit 1
    elif [ "$CSV_COUNT" -gt 1 ]; then
        echo -e "${RED}[ERROR] Found $CSV_COUNT CSV files in input_csv/. There should only be one.${NC}"
        exit 1
    fi

    CSV_FILE=$(find "${SCRIPT_DIR}/input_csv" -maxdepth 1 -name "*.csv")
    echo -e "  CSV file found: ${GREEN}$(basename "$CSV_FILE")${NC}"

    # Tipo di anonimizzazione
    while true; do
        echo ""
        echo -e "${BOLD}Select the extraction mode:${NC}"
        echo ""
        echo -e "  ${GREEN}1)${NC} Standard (clear) - no anonymization"
        echo -e "  ${GREEN}2)${NC} Anonymized (irreversible) - irreversibile hash"
        echo -e "  ${GREEN}3)${NC} Pseudonymized  (partial) - reversible AWS KMS encryption"
        echo ""
        read -p "Choice [1/2/3]: " ANON_CHOICE

        case "$ANON_CHOICE" in
            1) ANON_TYPE="clear"; break;;
            2) ANON_TYPE="irreversible"; break;;
            3) ANON_TYPE="partial"; break;;
            *)
                echo -e "${RED}[ERROR] Invalid choice. Please try again.${NC}"
                echo ""
                ;;
        esac
    done

    # Verifica credenziali AWS per partial
    if [ "$ANON_TYPE" == "partial" ]; then
        if [ -z "${AWS_KMS_KEY_ID}" ] && ! grep -q "AWS_KMS_KEY_ID" "${SCRIPT_DIR}/.env" 2>/dev/null; then
            echo -e "${YELLOW}[WARNING] For the 'partial' mode, AWS credentials are required.${NC}"
            echo -e "${YELLOW}Check that AWS_KMS_KEY_ID and AWS_REGION are configured in the .env file${NC}"
            read -p "Do you want to continue anyway? [Y/N]: " CONTINUE
            if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
                exit 1
            fi
        fi
    fi

    # Directory di output
    OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
    mkdir -p "$OUTPUT_DIR"

    # Riepilogo
    while true; do
        echo ""
        echo -e "${BOLD}${CYAN} Summary ${NC}"
        echo -e "  Mode:              ${GREEN}Extraction + QA${NC}"
        echo -e "  CSV File:          ${CSV_FILE}"
        echo -e "  Anonymization:     ${ANON_TYPE}"
        echo -e "  Output:            ${OUTPUT_DIR}"
        echo ""
        read -p "Confirm? [Y/N]: " CONFIRM
        if [ "$CONFIRM" == "n" ] || [ "$CONFIRM" == "N" ]; then
            echo "Operation canceled."
            exit 0
        elif [ "$CONFIRM" == "y" ] || [ "$CONFIRM" == "Y" ]; then
            echo "Preparing to start the pipeline..."
            echo ""
            break
        else
            echo "[ERROR] Invalid input, please try again"
            echo ""
        fi
    done

    # Lancia pipeline Nextflow
    echo ""
    echo -e "${BOLD}${GREEN}Starting pipeline...${NC}"
    echo ""

    nextflow run "${SCRIPT_DIR}/pipeline.nf" \
        --mode csv \
        --csv_file "$CSV_FILE" \
        --anonymization_type "$ANON_TYPE" \
        --out_dir "$OUTPUT_DIR" \
        --root_dir "$SCRIPT_DIR"


# Modalità locale

elif [ "$PIPELINE_MODE" == "local" ]; then
    echo ""
    echo -e "${BOLD}${CYAN}Mode: QA on local files${NC}"
    echo ""

    # Directory DICOM
    DATA_DIR="${DEFAULT_DATA_DIR}"
    mkdir -p "$DATA_DIR"

    # Directory di output
    OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
    mkdir -p "$OUTPUT_DIR"

    # Riepilogo
    while true; do
        echo ""
        echo -e "${BOLD}${CYAN} Summary ${NC}"
        echo -e "  Mode:          ${GREEN}QA on local files${NC}"
        echo -e "  DICOM dir:     ${DATA_DIR}"
        echo -e "  Output:        ${OUTPUT_DIR}"
        echo ""
        read -p "Confirm? [Y/N]: " CONFIRM
        if [ "$CONFIRM" == "n" ] || [ "$CONFIRM" == "N" ]; then
            echo "Operation canceled."
            exit 0
        elif [ "$CONFIRM" == "y" ] || [ "$CONFIRM" == "Y" ]; then
            echo "Preparing to start the pipeline..."
            echo ""
            break
        else
            echo "[ERROR] Invalid input, please try again"
            echo ""
        fi
    done

    # Lancia pipeline Nextflow
    echo ""
    echo -e "${BOLD}${GREEN}Starting pipeline...${NC}"
    echo ""

    nextflow run "${SCRIPT_DIR}/pipeline.nf" \
        --mode local \
        --data_dir "$DATA_DIR" \
        --out_dir "$OUTPUT_DIR" \
        --root_dir "$SCRIPT_DIR"
fi

echo ""
echo -e "${BOLD}${GREEN}   Pipeline completed! Report available in: ${OUTPUT_DIR} ${NC}"
echo ""
