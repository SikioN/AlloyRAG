import os
import pandas as pd
from dotenv import load_dotenv
from alloyrag.rag_system import get_rag_instance
from alloyrag.utils import logger

load_dotenv()


def create_sample_excel(filepath: str):
    """Generate a high-quality materials science catalog Excel template if none exists."""
    logger.info(f"Generating sample Excel file at {filepath}...")

    # Sheet 1: Alloys
    alloys_data = {
        "AlloyName": [
            "Ni-Superalloy-718",
            "Ti-6Al-4V-Grade5",
            "AISI-316L-Steel",
            "Al-Zn-Mg-Cu-7075",
        ],
        "Composition": [
            "Ni 52.5%, Cr 19.0%, Fe 18.5%, Nb 5.1%, Mo 3.0%, Ti 0.9%, Al 0.5%",
            "Ti 90%, Al 6%, V 4%",
            "Fe 68%, Cr 17%, Ni 12%, Mo 2.5%, Mn 2%, Si 0.75%",
            "Al 90%, Zn 5.6%, Mg 2.5%, Cu 1.6%, Cr 0.23%",
        ],
        "Description": [
            "Nickel-chromium-based superalloy, precipitation hardenable, high strength and temperature resistance.",
            "Alpha-beta titanium alloy, high specific strength and exceptional corrosion resistance.",
            "Austenitic chromium-nickel stainless steel, molybdenum-bearing, superior corrosion resistance.",
            "Ultra-high strength aluminum alloy, precipitation hardened, used in aerospace structures.",
        ],
    }

    # Sheet 2: Experiments (Modes & Properties)
    experiments_data = {
        "ExperimentID": ["EXP-001", "EXP-002", "EXP-003", "EXP-004", "EXP-005"],
        "AlloyName": [
            "Ni-Superalloy-718",
            "Ni-Superalloy-718",
            "Ti-6Al-4V-Grade5",
            "AISI-316L-Steel",
            "Al-Zn-Mg-Cu-7075",
        ],
        "ProcessingMode": [
            "Vacuum Annealing (980°C for 2h) + Water Quench",
            "Double Aging (720°C for 8h + 620°C for 8h) + Air Cool",
            "Hot Isostatic Pressing (HIP) at 920°C / 100 MPa for 4h",
            "Cold Rolling (70% thickness reduction) + Anneal 650°C",
            "Solution Heat Treatment (480°C for 1h) + Artificial Aging (120°C for 24h)",
        ],
        "TestingEquipment": [
            "Instron-5982 Tensile Tester",
            "Vickers Microhardness Tester Wilson VH1202",
            "Instron-5982 Tensile Tester",
            "Scanning Electron Microscope Leo-1450",
            "Vickers Microhardness Tester Wilson VH1202",
        ],
        "PropertyName": [
            "Yield Strength",
            "Vickers Hardness",
            "Tensile Strength",
            "Grain Size",
            "Vickers Hardness",
        ],
        "PropertyValue": ["1030 MPa", "440 HV", "950 MPa", "12 micrometers", "175 HV"],
        "ResearcherName": [
            "Dr. Ivan Ivanov (Lab 4)",
            "Dr. Anna Petrova (Lab 2)",
            "Dr. Ivan Ivanov (Lab 4)",
            "Dr. Sergey Sidorov (Microscopy Lab)",
            "Dr. Anna Petrova (Lab 2)",
        ],
        "Outcome": [
            "Achieved moderate ductility with high yield strength due to gamma-prime phase precipitation.",
            "Optimal hardness profile, double aging facilitated fine gamma-double-prime formation.",
            "Closed internal voids and porosity, improving elongation by 15% without sacrificing strength.",
            "Recrystallization occurred fully; fine equiaxed grain structure observed.",
            "Peak age condition achieved with homogeneous distribution of Eta-prime precipitates.",
        ],
    }

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        pd.DataFrame(alloys_data).to_excel(writer, sheet_name="Alloys", index=False)
        pd.DataFrame(experiments_data).to_excel(
            writer, sheet_name="Experiments", index=False
        )

    logger.info("Sample Excel created successfully!")


def extract_excel_to_kg(filepath: str) -> dict | None:
    """Read structured sheets and extract as custom KG dict synchronously (CPU-bound)."""
    if not os.path.exists(filepath):
        # Auto-create if it's the template filepath
        if "experiments_template" in filepath:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            create_sample_excel(filepath)
        else:
            logger.error(f"Excel file not found at: {filepath}")
            return None

    logger.info(f"Reading structured Excel catalog from {filepath}...")

    # Try reading two sheets (Alloys and Experiments)
    xls = pd.ExcelFile(filepath)
    sheets = xls.sheet_names

    alloys_df = None
    experiments_df = None

    if "Alloys" in sheets:
        alloys_df = pd.read_excel(filepath, sheet_name="Alloys")
    if "Experiments" in sheets:
        experiments_df = pd.read_excel(filepath, sheet_name="Experiments")

    # Fallback to single sheet if format differs
    if experiments_df is None and len(sheets) > 0:
        experiments_df = pd.read_excel(filepath, sheet_name=sheets[0])
        logger.info(f"Loaded sheet '{sheets[0]}' as main experimental table.")

    custom_kg = {"chunks": [], "entities": [], "relationships": []}

    # 1. Create a document chunk for the Excel catalog summary to ground the items in search
    doc_id = f"excel_{os.path.basename(filepath)}"
    chunk_content = f"Каталог экспериментальных данных по материаловедению из файла {os.path.basename(filepath)}.\n"
    if alloys_df is not None:
        chunk_content += f"Зарегистрировано сплавов: {len(alloys_df)}. Список сплавов: {', '.join(alloys_df['AlloyName'].astype(str).tolist())}.\n"
    if experiments_df is not None:
        chunk_content += f"Зарегистрировано экспериментов: {len(experiments_df)}."

    custom_kg["chunks"].append(
        {"content": chunk_content, "source_id": doc_id, "file_path": filepath}
    )

    # 2. Extract Alloys
    if alloys_df is not None:
        for _, row in alloys_df.iterrows():
            alloy = str(row.get("AlloyName", "")).strip()
            comp = str(row.get("Composition", "")).strip()
            desc = str(row.get("Description", "")).strip()

            if not alloy or alloy == "nan":
                continue

            alloy_desc = f"Сплав {alloy}. Состав: {comp}. Описание: {desc}"
            custom_kg["entities"].append(
                {
                    "entity_name": alloy,
                    "entity_type": "Alloy",
                    "description": alloy_desc,
                    "source_id": doc_id,
                    "file_path": filepath,
                }
            )

    # 3. Extract Experiments (Alloys, Modes, Properties, Equipment, Researchers)
    if experiments_df is not None:
        for idx, row in experiments_df.iterrows():
            exp_id = str(row.get("ExperimentID", f"EXP-{idx + 1:03d}")).strip()
            alloy = str(row.get("AlloyName", "")).strip()
            mode = str(row.get("ProcessingMode", "")).strip()
            equipment = str(row.get("TestingEquipment", "")).strip()
            prop_name = str(row.get("PropertyName", "")).strip()
            prop_val = str(row.get("PropertyValue", "")).strip()
            researcher = str(row.get("ResearcherName", "")).strip()
            outcome = str(row.get("Outcome", "")).strip()

            # Skip invalid rows
            if not alloy or alloy == "nan" or not mode or mode == "nan":
                continue

            # Define entity names
            mode_entity = f"Режим_{exp_id}"
            prop_entity = f"Свойство_{exp_id}"

            # Add Mode Entity
            custom_kg["entities"].append(
                {
                    "entity_name": mode_entity,
                    "entity_type": "Mode",
                    "description": f"Режим обработки для эксперимента {exp_id} сплава {alloy}: {mode}.",
                    "source_id": doc_id,
                    "file_path": filepath,
                }
            )

            # Add Property Entity
            custom_kg["entities"].append(
                {
                    "entity_name": prop_entity,
                    "entity_type": "Property",
                    "description": f"Измеренное свойство в эксперименте {exp_id} сплава {alloy}: {prop_name} = {prop_val}.",
                    "source_id": doc_id,
                    "file_path": filepath,
                }
            )

            # Add Equipment if present
            if equipment and equipment != "nan":
                custom_kg["entities"].append(
                    {
                        "entity_name": equipment,
                        "entity_type": "Equipment",
                        "description": f"Исследовательское оборудование: {equipment}.",
                        "source_id": doc_id,
                        "file_path": filepath,
                    }
                )
                # Connect Property/Experiment to Equipment
                custom_kg["relationships"].append(
                    {
                        "src_id": prop_entity,
                        "tgt_id": equipment,
                        "description": f"Свойство {prop_name} ({prop_val}) измерено на установке {equipment}.",
                        "keywords": "measured_by,equipment",
                        "source_id": doc_id,
                        "file_path": filepath,
                    }
                )

            # Add Researcher if present
            if researcher and researcher != "nan":
                custom_kg["entities"].append(
                    {
                        "entity_name": researcher,
                        "entity_type": "ResearchTeam",
                        "description": f"Исследователь/команда: {researcher}.",
                        "source_id": doc_id,
                        "file_path": filepath,
                    }
                )
                # Connect Alloy / Experiment to Researcher
                custom_kg["relationships"].append(
                    {
                        "src_id": mode_entity,
                        "tgt_id": researcher,
                        "description": f"Эксперимент с режимом {mode} проведен исследователем {researcher}.",
                        "keywords": "conducted_by,researcher",
                        "source_id": doc_id,
                        "file_path": filepath,
                    }
                )

            # Relationships linking Alloy -> Mode -> Property
            custom_kg["relationships"].append(
                {
                    "src_id": alloy,
                    "tgt_id": mode_entity,
                    "description": f"Сплав {alloy} был обработан в режиме: {mode}.",
                    "keywords": "processed_by,treatment",
                    "source_id": doc_id,
                    "file_path": filepath,
                }
            )

            custom_kg["relationships"].append(
                {
                    "src_id": mode_entity,
                    "tgt_id": prop_entity,
                    "description": f"Обработка в режиме {mode} привела к свойствам: {prop_name} = {prop_val}. Результат: {outcome}.",
                    "keywords": "resulted_in,effect",
                    "source_id": doc_id,
                    "file_path": filepath,
                }
            )

            custom_kg["relationships"].append(
                {
                    "src_id": alloy,
                    "tgt_id": prop_entity,
                    "description": f"Сплав {alloy} обладает свойством {prop_name} со значением {prop_val}. Описание: {outcome}.",
                    "keywords": "exhibits_property,strength",
                    "source_id": doc_id,
                    "file_path": filepath,
                }
            )

    return custom_kg


async def aingest_excel_file(filepath: str):
    """Read structured sheets and index as direct custom KG entities and relationships."""
    custom_kg = extract_excel_to_kg(filepath)
    if custom_kg is None:
        return False

    # Ingest via custom KG insert
    rag = get_rag_instance()
    await rag.initialize_storages()
    doc_id = f"excel_{os.path.basename(filepath)}"
    logger.info(
        f"Ingesting {len(custom_kg['entities'])} entities and {len(custom_kg['relationships'])} relations into AlloyRAG..."
    )

    # Call async method
    await rag.ainsert_custom_kg(custom_kg, full_doc_id=doc_id)

    logger.info(f"Successfully finished Excel ingestion for {filepath}.")
    return True


def ingest_excel_file(filepath: str) -> bool:
    """Synchronous wrapper for ingest_excel_file."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                lambda: asyncio.run(aingest_excel_file(filepath))
            ).result()
    else:
        return asyncio.run(aingest_excel_file(filepath))


if __name__ == "__main__":
    import sys

    # Use template filepath by default if none provided
    target_file = "./inputs/experiments_template.xlsx"
    if len(sys.argv) > 1:
        target_file = sys.argv[1]

    ingest_excel_file(target_file)
