type ReaderLanguage = "source" | "target";
type ReaderMode = "offline" | "online";
type ReaderView = "both" | ReaderLanguage;

interface BookChapter {
  id: string;
  sourceTitle: string;
  targetTitle?: string | null;
  sourceDataFile: string;
  targetDataFile?: string | null;
  segmentIds: string[];
}

interface TocEntry {
  segmentId: string;
  chapterId: string;
  level: number;
  title: string;
}

interface BookDocument {
  schemaVersion: number;
  slug: string;
  title: string;
  readerTitle: string;
  description: string;
  sourceLanguage: string;
  sourceLabel: string;
  sourceHtmlLang: string;
  hasOfflineTranslation?: boolean;
  targetLanguage?: string | null;
  targetLabel?: string | null;
  targetHtmlLang?: string | null;
  segmentCount: number;
  initialChapterId: string;
  chapters: BookChapter[];
  toc: TocEntry[];
  generatedAt: string;
  mathjax: {
    packages: string[];
    macros: Record<string, string>;
  };
}

interface BookChunk {
  schemaVersion: number;
  slug: string;
  chapterId: string;
  language: ReaderLanguage;
  html: string;
}

interface CatalogEntry {
  title: string;
  description?: string | null;
  sourceLabel?: string | null;
  targetLabel?: string | null;
  dataFile: string;
}

interface BookCatalog {
  schemaVersion: number;
  defaultBook: string;
  books: Record<string, CatalogEntry>;
}

interface ReadingState {
  bookSlug?: string;
  chapterId?: string | null;
  segmentId?: string | null;
  progressPercent?: number | null;
  sourceScrollTop?: number | null;
  targetScrollTop?: number | null;
  lastOpenedAt?: number | null;
  updatedAt?: number | null;
}

interface ReadingPosition {
  chapterId: string;
  segmentId: string;
  progressPercent?: number;
  sourceScrollTop: number | null;
  targetScrollTop: number | null;
}

interface SettingsField {
  name: string;
  label: string;
  description: string;
  note: string | null;
  group: string;
  inputType: "text" | "number" | "url" | "password" | "json" | "path";
  value: string | null;
  defaultValue: string | null;
  isSet: boolean;
  sensitive: boolean;
}

interface SettingsDocument {
  source: string;
  fields: SettingsField[];
  restartRequired: boolean;
}

interface ReaderAppState {
  mode: ReaderMode;
  view: ReaderView;
  offlineView: ReaderView;
  activeId: string | null;
  syncLock: boolean;
  toastTimer: number | null;
  popoverAnchor: HTMLElement | null;
  popoverReturnFocus: HTMLElement | null;
  tocOpen: boolean;
  liveTargetLanguage: string;
  liveRequestId: number;
  liveController: AbortController | null;
  chapterRequestId: number;
  currentChapterId: string | null;
  currentTocId: string | null;
  resumePosition: ReadingPosition | null;
  readingPositionTimer: number | null;
  pendingReadingSegmentId: string | null;
  mathReady: boolean;
  mathQueue: Promise<void>;
  chunkPromises: Map<string, Promise<BookChunk>>;
  chaptersById: Map<string, BookChapter>;
  chapterIndexes: Map<string, number>;
  segmentChapters: Map<string, string>;
  segmentIndexes: Map<string, number>;
  tocLinks: Map<string, HTMLButtonElement>;
  scrollFrames: Record<ReaderLanguage, number | null>;
  segmentLists: Record<ReaderLanguage, HTMLElement[]>;
  segmentMaps: Record<ReaderLanguage, Map<string, HTMLElement>>;
}

interface BookViewerPreferencesApi {
  ready: Promise<void>;
  read(slug: string): ReadingState;
  touch(slug: string): void;
  savePosition(slug: string, position: ReadingPosition): void;
  lastOpenedAt(slug: string): number;
  progressPercent(slug: string): number;
}

interface BookViewerApi {
  initialize(documentData: BookDocument): void;
  showLoadError(message: string): void;
}

interface BookViewerDomApi {
  requiredElement<ElementType extends Element>(
    selector: string,
    elementType: new () => ElementType,
  ): ElementType;
  matchingElements<ElementType extends Element>(
    root: ParentNode,
    selector: string,
    elementType: new () => ElementType,
  ): ElementType[];
}

interface MathJaxApi {
  loader?: {
    load: string[];
  };
  tex?: {
    packages: { "[+]": string[] };
    inlineMath: string[][];
    displayMath: string[][];
    tags: string;
    macros: Record<string, string>;
  };
  options?: {
    enableMenu: boolean;
    skipHtmlTags: string[];
  };
  startup?: {
    typeset?: boolean;
    ready?: () => void;
    defaultReady?: () => void;
    promise?: Promise<void>;
  };
  typesetClear?: (elements: Element[]) => void;
  typesetPromise?: (elements: Element[]) => Promise<void>;
}

interface Window {
  BOOK_VIEWER_CATALOG?: BookCatalog;
  BOOK_VIEWER_DOCUMENT?: BookDocument;
  BOOK_VIEWER_CHUNKS?: Record<string, BookChunk>;
  BookViewer: BookViewerApi;
  BookViewerDom: BookViewerDomApi;
  BookViewerPreferences: BookViewerPreferencesApi;
  MathJax?: MathJaxApi;
}
