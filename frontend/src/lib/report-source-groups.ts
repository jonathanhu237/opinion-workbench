import type { ReportSection } from '@/lib/api/topic-reports'

type Source = ReportSection['sources'][number]['source']

// Presentation-only grouping: never merge database records or guess that
// different statements concern the same event. Preserve wording and numbers.
function textKey(source: Source) {
  const text = source.snippet
  if (text.length >= 1000) return null // A capped preview may hide differences.
  const normalized = text
    .normalize('NFKC')
    .replace(/\uE627[^\uE627\s]{1,40}?超话/gu, '')
    .replace(/@[\p{L}\p{N}_-]+(?=[\s@#]|$)/gu, '')
    .replace(/收起d\s*$/u, '')
    .replace(/[\s\u200B-\u200D\uFEFF\uE000-\uF8FF#]/gu, '')
  return normalized.length >= 80 ? `${source.platform}:${normalized}` : null
}

export function groupReportSources(sources: Source[]) {
  const groups: { source: Source; count: number; sources: Source[] }[] = []
  const byText = new Map<string, number>()
  const urls = new Set<string>()
  for (const source of sources) {
    if (urls.has(source.content_url)) continue
    urls.add(source.content_url)
    const key = textKey(source)
    const index = key ? byText.get(key) : undefined
    if (index !== undefined) {
      groups[index].count += 1
      groups[index].sources.push(source)
    } else {
      if (key) byText.set(key, groups.length)
      groups.push({ source, count: 1, sources: [source] })
    }
  }
  return groups
}

type ReadingParagraph = { text: string; sources: Source[] }

// Group adjacent citation-equivalent paragraphs, not guessed events. Keep every
// word and the original order: a source can itself describe several events.
// Resolve text families across the report so [A,B,C] and [A,B] share references
// only when A/B/C really have the same long text (not merely an overlapping ID).
export function groupReadingParagraphs(paragraphs: ReadingParagraph[]) {
  const families = new Map<string, number>()
  groupReportSources(
    paragraphs.flatMap((paragraph) => paragraph.sources),
  ).forEach((group, index) =>
    group.sources.forEach((source) => families.set(source.content_url, index)),
  )
  const blocks: { texts: string[]; sources: Source[]; citationKey: string }[] =
    []
  for (const paragraph of paragraphs) {
    const citationKey = [
      ...new Set(
        paragraph.sources.map((source) => families.get(source.content_url)!),
      ),
    ]
      .sort((a, b) => a - b)
      .join(',')
    const previous = blocks.at(-1)
    if (citationKey && previous?.citationKey === citationKey) {
      previous.texts.push(paragraph.text)
      previous.sources = [
        ...new Map(
          [...previous.sources, ...paragraph.sources].map((source) => [
            source.content_url,
            source,
          ]),
        ).values(),
      ]
    } else {
      blocks.push({
        texts: [paragraph.text],
        sources: [...paragraph.sources],
        citationKey,
      })
    }
  }
  return blocks.map(({ texts, sources }) => ({
    texts,
    groups: groupReportSources(sources),
  }))
}
