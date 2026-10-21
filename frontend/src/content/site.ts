/**
 * Marketing copy shared by the landing page and the app. Everything listed
 * here is implemented in version 1 — keep it that way when editing.
 */
import type { LucideIcon } from "lucide-react";
import {
  ArrowDownUp,
  BarChart3,
  CaseSensitive,
  Copy,
  Eraser,
  FileSearch,
  FileSpreadsheet,
  GitCompareArrows,
  History,
  Replace,
  ShieldCheck,
  SquareDashed,
  TableProperties,
  Type,
  Undo2,
  WandSparkles,
  Banknote,
  Flag,
  Globe,
  ListChecks,
  Mail,
  Phone,
  Sparkles,
  Split,
  Users,
  Zap,
} from "lucide-react";

export const SITE = {
  name: "CleanData Studio",
  tagline: "Clean Your Data. Trust Your Results.",
  description: "A simple and powerful workspace to inspect, clean, and export better datasets.",
};

export const CONTACT_EMAIL = (import.meta.env.VITE_CONTACT_EMAIL as string | undefined)?.trim() || "";
export const GITHUB_URL = (import.meta.env.VITE_GITHUB_URL as string | undefined)?.trim() || "";

export type Feature = { icon: LucideIcon; title: string; description: string };

export const FEATURES: Feature[] = [
  {
    icon: BarChart3,
    title: "Instant data quality report",
    description: "Missing values, duplicates, column types and completeness — plus extra spaces, placeholders like “N/A”, mixed types and outliers — found the moment your file is uploaded.",
  },
  {
    icon: FileSearch,
    title: "Preview before you apply",
    description: "Every operation shows exactly which rows, columns and cells will change before anything is modified.",
  },
  {
    icon: Undo2,
    title: "Undo and reset",
    description: "Step back one operation at a time, or restore the original upload. The original data is never overwritten.",
  },
  {
    icon: GitCompareArrows,
    title: "Before-and-after comparison",
    description: "See row, column, missing-value and duplicate counts side by side, with a log of every change.",
  },
  {
    icon: FileSpreadsheet,
    title: "CSV, Excel and JSON",
    description: "Import CSV, TSV, Excel (.xlsx, .xls) and JSON files up to {limit}. Download results as CSV or Excel.",
  },
  {
    icon: Zap,
    title: "Quick Clean and reusable recipes",
    description: "One click proposes every safe fix. Save the steps as a recipe and repeat them on next week's file, then send the client a ready-made change report.",
  },
  {
    icon: Sparkles,
    title: "Optional AI assistant",
    description: "Describe the cleaning in your own words or ask questions about the data. The AI only chooses the app's own steps; every answer is calculated from your data and previewed first.",
  },
  {
    icon: ShieldCheck,
    title: "Private by design",
    description: "No account required. Data is processed on the server and deleted after inactivity. The optional AI assistant never receives the full file.",
  },
];

export type OperationInfo = { icon: LucideIcon; title: string; description: string };

export const OPERATIONS: OperationInfo[] = [
  { icon: Copy, title: "Remove duplicate rows", description: "Keep the first or last occurrence of exact duplicates." },
  { icon: SquareDashed, title: "Handle missing values", description: "Drop rows or columns, or fill with mean, median or a value." },
  { icon: Eraser, title: "Trim whitespace", description: "Remove leading and trailing spaces, keep internal spacing." },
  { icon: CaseSensitive, title: "Standardize text", description: "Convert to lowercase, UPPERCASE or Title Case." },
  { icon: TableProperties, title: "Clean column names", description: "Trim, replace spaces with underscores, avoid collisions." },
  { icon: Type, title: "Convert data types", description: "Integer, decimal, text or date — with invalid values reported." },
  { icon: ArrowDownUp, title: "Review outliers", description: "IQR-based detection for numeric columns. Review only, never auto-deleted." },
  { icon: WandSparkles, title: "Remove empty rows/columns", description: "Drop rows or columns that contain no values at all." },
  { icon: Replace, title: "Find and replace", description: "Replace exact values or text fragments in selected columns." },
  { icon: ListChecks, title: "Map many values at once", description: "Turn “Isb”, “ISB” and “islamabad” into one spelling from a table." },
  { icon: Phone, title: "Phone numbers, any country", description: "One national, international or E.164 format; invalid numbers reported." },
  { icon: Globe, title: "Country names and codes", description: "“USA”, “U.S.A.” and “america” become “United States” or an ISO code." },
  { icon: Mail, title: "Clean email addresses", description: "Remove spaces, capitals and “mailto:”, fix common typos, list invalid ones." },
  { icon: Banknote, title: "Amounts in any currency", description: "“$1,250.00”, “Rs 1,25,000” and “1.234,56 €” become real numbers." },
  { icon: Split, title: "Split and merge columns", description: "Full name into first and last name, or several columns into one." },
  { icon: Users, title: "Near-duplicates", description: "Find the same record written differently, even with small spelling mistakes." },
  { icon: Flag, title: "Flag rows for review", description: "Missing, invalid or out-of-range values (age 0–100), without changing data." },
  { icon: TableProperties, title: "Organize columns and sort", description: "Rename, remove and reorder columns for a CRM import; sort rows." },
  { icon: FileSpreadsheet, title: "Coloured Excel download", description: "Cells that still need a look are highlighted, with a colour key." },
  { icon: History, title: "Activity log", description: "Every applied step is recorded with what it changed." },
];

export const STEPS = [
  {
    title: "Upload your data",
    description: "Drag and drop a CSV, TSV, Excel or JSON file up to {limit}. It is validated and parsed without changing your values.",
  },
  {
    title: "Inspect and clean",
    description: "Review the quality report, preview each cleaning operation, and apply only what you choose.",
  },
  {
    title: "Compare and download",
    description: "Check the before-and-after summary, then download the cleaned file as CSV or Excel.",
  },
];

export const FAQ = [
  {
    q: "Which file types are supported?",
    a: "You can upload CSV, TSV, Excel (.xlsx and older .xls) and JSON (an array of records or JSON Lines) up to {limit}, and download results as CSV or Excel. PDFs, images and Word documents are not supported because they are not data tables.",
  },
  {
    q: "Do I need an account?",
    a: "No. Open the workspace and upload a file. There is no registration and nothing to install in your browser.",
  },
  {
    q: "Where is my data processed?",
    a: "Your file is uploaded to the CleanData Studio server. While it is being imported it is held in a private temporary file, which is deleted as soon as the import finishes; after that the data lives only in the server's memory. It is not shared with other users or sent to third-party APIs. The optional AI assistant receives only a short description of your columns (names, types, counts and a few example values), never the full file; by default it runs on the same computer as the app (Ollama), and if a site uses a cloud AI instead, the app asks for your permission before anything is sent. When you run the app on your own computer, the server is your computer.",
  },
  {
    q: "How long is my data kept?",
    a: "Only while you are working. A session is deleted after {ttl} of inactivity, when you start a new file, or when the server restarts. Download your cleaned file before leaving.",
  },
  {
    q: "Can I undo a change?",
    a: "Yes. Undo reverses the last applied operation, and Reset restores the dataset exactly as it was uploaded. The original upload is kept separately and never modified.",
  },
  {
    q: "Are outliers removed automatically?",
    a: "No. Outlier detection only highlights values outside the IQR range so you can review them. An outlier is not necessarily an error.",
  },
];
