/// Data models shared across the app (mirrors the backend JSON contracts).
library;

class VoterResult {
  final int id;
  final String name;
  final String relationName;
  final String relationType;
  final String epic;
  final String serial;
  final String part;
  final String house;
  final String age;
  final String gender;
  final int page;
  final String pdf; // relative id, e.g. "Tirhe/Part_101.pdf"
  final String pdfName;
  final String village;
  final double score;

  const VoterResult({
    required this.id,
    required this.name,
    required this.relationName,
    required this.relationType,
    required this.epic,
    required this.serial,
    required this.part,
    required this.house,
    required this.age,
    required this.gender,
    required this.page,
    required this.pdf,
    required this.pdfName,
    required this.village,
    required this.score,
  });

  factory VoterResult.fromJson(Map<String, dynamic> j) => VoterResult(
    id: (j['id'] as num?)?.toInt() ?? 0,
    name: j['name'] as String? ?? '',
    relationName: j['relation_name'] as String? ?? '',
    relationType: j['relation_type'] as String? ?? '',
    epic: j['epic'] as String? ?? '',
    serial: j['serial'] as String? ?? '',
    part: j['part'] as String? ?? '',
    house: j['house'] as String? ?? '',
    age: j['age'] as String? ?? '',
    gender: j['gender'] as String? ?? '',
    page: (j['page'] as num?)?.toInt() ?? 1,
    pdf: j['pdf'] as String? ?? '',
    pdfName: j['pdf_name'] as String? ?? (j['pdf'] as String? ?? ''),
    village: j['village'] as String? ?? '',
    score: (j['score'] as num?)?.toDouble() ?? 0,
  );

  String get relationLabel {
    switch (relationType.toLowerCase()) {
      case 'husband':
        return 'पतीचे नाव';
      case 'mother':
        return 'आईचे नाव';
      case 'father':
        return 'वडिलांचे नाव';
      default:
        return 'वडिलांचे / पतीचे नाव';
    }
  }

  /// English label matching the original electoral-roll voter slip
  /// ("Name : ... / Husband's Name : ..." style), used by [VoterSlipCard].
  String get relationLabelEn {
    switch (relationType.toLowerCase()) {
      case 'husband':
        return "Husband's Name";
      case 'wife':
        return "Wife's Name";
      case 'mother':
        return "Mother's Name";
      case 'father':
        return "Father's Name";
      case 'guardian':
        return "Guardian's Name";
      case 'other':
        return "Other's Name";
      default:
        return "Father's / Husband's Name";
    }
  }
}

class DuplicateRecord {
  final int id;
  final String name;
  final String relationName;
  final String epic;
  final String serial;
  final int page;
  final String village;
  final String pdf;
  final String pdfName;

  const DuplicateRecord({
    required this.id,
    required this.name,
    required this.relationName,
    required this.epic,
    required this.serial,
    required this.page,
    required this.village,
    required this.pdf,
    required this.pdfName,
  });

  factory DuplicateRecord.fromJson(Map<String, dynamic> j) => DuplicateRecord(
    id: (j['id'] as num?)?.toInt() ?? 0,
    name: j['name'] as String? ?? '',
    relationName: j['relation_name'] as String? ?? '',
    epic: j['epic'] as String? ?? '',
    serial: j['serial'] as String? ?? '',
    page: (j['page'] as num?)?.toInt() ?? 1,
    village: j['village'] as String? ?? '',
    pdf: j['pdf'] as String? ?? '',
    pdfName: j['pdf_name'] as String? ?? '',
  );
}

class DuplicateGroup {
  final String key;
  final String label;
  final String relationLabel;
  final List<DuplicateRecord> records;

  const DuplicateGroup({
    required this.key,
    required this.label,
    required this.relationLabel,
    required this.records,
  });

  factory DuplicateGroup.fromJson(Map<String, dynamic> j) => DuplicateGroup(
    key: j['key'] as String? ?? '',
    label: j['label'] as String? ?? '',
    relationLabel: j['relation_label'] as String? ?? '',
    records: ((j['records'] as List?) ?? const [])
        .map((e) => DuplicateRecord.fromJson(e as Map<String, dynamic>))
        .toList(),
  );
}

class DuplicateOverview {
  final List<DuplicateGroup> epic;
  final List<DuplicateGroup> name;
  final List<DuplicateGroup> sameRelativeAcrossVillages;
  final List<DuplicateGroup> differentRelativeAcrossVillages;
  final bool crossVillageSetupRequired;

  const DuplicateOverview({
    required this.epic,
    required this.name,
    required this.sameRelativeAcrossVillages,
    required this.differentRelativeAcrossVillages,
    required this.crossVillageSetupRequired,
  });

  factory DuplicateOverview.fromJson(Map<String, dynamic> j) =>
      DuplicateOverview(
        epic: ((j['epic'] as List?) ?? const [])
            .map((e) => DuplicateGroup.fromJson(e as Map<String, dynamic>))
            .toList(),
        name: ((j['name'] as List?) ?? const [])
            .map((e) => DuplicateGroup.fromJson(e as Map<String, dynamic>))
            .toList(),
        sameRelativeAcrossVillages: ((j['same_relative'] as List?) ?? const [])
            .map((e) => DuplicateGroup.fromJson(e as Map<String, dynamic>))
            .toList(),
        differentRelativeAcrossVillages:
            ((j['different_relative'] as List?) ?? const [])
                .map((e) => DuplicateGroup.fromJson(e as Map<String, dynamic>))
                .toList(),
        crossVillageSetupRequired: j['setup_required'] == true,
      );
}

class SearchResponse {
  final List<VoterResult> results;
  final int total;
  final int page;
  final int pageSize;
  final double tookMs;
  final Map<String, dynamic> query;
  final bool relaxed;
  final List<String> suggestions;

  const SearchResponse({
    required this.results,
    required this.total,
    required this.page,
    required this.pageSize,
    required this.tookMs,
    required this.query,
    required this.relaxed,
    required this.suggestions,
  });

  factory SearchResponse.fromJson(Map<String, dynamic> j) => SearchResponse(
    results: ((j['results'] as List?) ?? const [])
        .map((e) => VoterResult.fromJson(e as Map<String, dynamic>))
        .toList(),
    total: (j['total'] as num?)?.toInt() ?? 0,
    page: (j['page'] as num?)?.toInt() ?? 1,
    pageSize: (j['page_size'] as num?)?.toInt() ?? 20,
    tookMs: (j['took_ms'] as num?)?.toDouble() ?? 0,
    query: (j['query'] as Map?)?.cast<String, dynamic>() ?? const {},
    relaxed: j['relaxed'] as bool? ?? false,
    suggestions: ((j['suggestions'] as List?) ?? const []).cast<String>(),
  );

  int get totalPages => total == 0 ? 0 : ((total - 1) ~/ pageSize) + 1;
}

/// Typeahead suggestion – a real voter entry from the index.
class Suggestion {
  final String text;
  final String name;
  final String relationName;
  final String relationType;
  final String village;
  final String pdf;
  final int page;
  final String age;
  final String gender;

  const Suggestion({
    required this.text,
    required this.name,
    required this.relationName,
    required this.relationType,
    required this.village,
    required this.pdf,
    required this.page,
    required this.age,
    required this.gender,
  });

  factory Suggestion.fromJson(Map<String, dynamic> j) => Suggestion(
    text: j['text'] as String? ?? '',
    name: j['name'] as String? ?? '',
    relationName: j['relation_name'] as String? ?? '',
    relationType: j['relation_type'] as String? ?? '',
    village: j['village'] as String? ?? '',
    pdf: j['pdf'] as String? ?? '',
    page: (j['page'] as num?)?.toInt() ?? 1,
    age: j['age'] as String? ?? '',
    gender: j['gender'] as String? ?? '',
  );
}

class Village {
  final String name;
  final int pdfs;
  final int records;

  const Village({required this.name, this.pdfs = 0, this.records = 0});

  factory Village.fromJson(Map<String, dynamic> j) => Village(
    name: j['name'] as String? ?? '',
    pdfs: (j['pdfs'] as num?)?.toInt() ?? 0,
    records: (j['records'] as num?)?.toInt() ?? 0,
  );
}

class PublicStats {
  final int totalPdfs;
  final int totalRecords;
  final int totalVillages;
  final String indexStatus;
  final int indexVersion;
  final String? lastIndexedAt;

  const PublicStats({
    required this.totalPdfs,
    required this.totalRecords,
    required this.totalVillages,
    required this.indexStatus,
    required this.indexVersion,
    this.lastIndexedAt,
  });

  factory PublicStats.fromJson(Map<String, dynamic> j) => PublicStats(
    totalPdfs: (j['total_pdfs'] as num?)?.toInt() ?? 0,
    totalRecords: (j['total_records'] as num?)?.toInt() ?? 0,
    totalVillages: (j['total_villages'] as num?)?.toInt() ?? 0,
    indexStatus: j['index_status'] as String? ?? 'empty',
    indexVersion: (j['index_version'] as num?)?.toInt() ?? 0,
    lastIndexedAt: j['last_indexed_at'] as String?,
  );
}

class IndexProgress {
  final int current; // pages done
  final int total; // pages total
  final double percent;
  final String file;
  final int filesDone;
  final int filesTotal;

  const IndexProgress({
    required this.current,
    required this.total,
    required this.percent,
    required this.file,
    this.filesDone = 0,
    this.filesTotal = 0,
  });

  factory IndexProgress.fromJson(Map<String, dynamic> j) => IndexProgress(
    current: (j['current'] as num?)?.toInt() ?? 0,
    total: (j['total'] as num?)?.toInt() ?? 0,
    percent: (j['percent'] as num?)?.toDouble() ?? 0,
    file: j['file'] as String? ?? '',
    filesDone: (j['files_done'] as num?)?.toInt() ?? 0,
    filesTotal: (j['files_total'] as num?)?.toInt() ?? 0,
  );
}

class IndexStatus {
  final String status; // empty | ready | indexing | error
  final int version;
  final String? lastIndexedAt;
  final double? lastDurationSec;
  final String? error;
  final int totalPdfs;
  final int indexedPdfs;
  final int totalRecords;
  final int totalVillages;
  final bool ocrAvailable;
  final IndexProgress progress;

  const IndexStatus({
    required this.status,
    required this.version,
    required this.lastIndexedAt,
    required this.lastDurationSec,
    required this.error,
    required this.totalPdfs,
    required this.indexedPdfs,
    required this.totalRecords,
    required this.totalVillages,
    required this.ocrAvailable,
    required this.progress,
  });

  factory IndexStatus.fromJson(Map<String, dynamic> j) => IndexStatus(
    status: j['status'] as String? ?? 'empty',
    version: (j['version'] as num?)?.toInt() ?? 0,
    lastIndexedAt: j['last_indexed_at'] as String?,
    lastDurationSec: (j['last_duration_sec'] as num?)?.toDouble(),
    error: j['error'] as String?,
    totalPdfs: (j['total_pdfs'] as num?)?.toInt() ?? 0,
    indexedPdfs: (j['indexed_pdfs'] as num?)?.toInt() ?? 0,
    totalRecords: (j['total_records'] as num?)?.toInt() ?? 0,
    totalVillages: (j['total_villages'] as num?)?.toInt() ?? 0,
    ocrAvailable: j['ocr_available'] as bool? ?? false,
    progress: IndexProgress.fromJson(
      (j['progress'] as Map?)?.cast<String, dynamic>() ?? const {},
    ),
  );

  bool get isIndexing => status == 'indexing';
}

class PdfFile {
  final String id;
  final String name;
  final String village;
  final int size;
  final int pages;
  final String uploadedAt;
  final bool indexed;
  final int records;
  final int ocrPages;
  final String status;
  final String error;

  const PdfFile({
    required this.id,
    required this.name,
    required this.village,
    required this.size,
    required this.pages,
    required this.uploadedAt,
    required this.indexed,
    required this.records,
    required this.ocrPages,
    required this.status,
    required this.error,
  });

  factory PdfFile.fromJson(Map<String, dynamic> j) => PdfFile(
    id: j['id'] as String? ?? '',
    name: j['name'] as String? ?? '',
    village: j['village'] as String? ?? '',
    size: (j['size'] as num?)?.toInt() ?? 0,
    pages: (j['pages'] as num?)?.toInt() ?? 0,
    uploadedAt: j['uploaded_at'] as String? ?? '',
    indexed: j['indexed'] as bool? ?? false,
    records: (j['records'] as num?)?.toInt() ?? 0,
    ocrPages: (j['ocr_pages'] as num?)?.toInt() ?? 0,
    status: j['status'] as String? ?? '',
    error: j['error'] as String? ?? '',
  );
}

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  const ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}
