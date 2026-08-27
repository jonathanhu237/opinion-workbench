export const MAX_RULE_NAME_LENGTH = 80
export const MAX_TERM_LENGTH = 100
export const MAX_TERMS_PER_RULE = 100
export const MAX_EXECUTABLE_TERMS = 20

export function codePointLength(value: string) {
  return Array.from(value).length
}

export function trimRuleValue(value: string) {
  // Match Python str.strip(): include NEL/C0 separators, but preserve U+FEFF.
  let start = 0
  let end = value.length
  while (start < end && isRuleWhitespace(value.charAt(start))) start += 1
  while (end > start && isRuleWhitespace(value.charAt(end - 1))) end -= 1
  return value.slice(start, end)
}

function isRuleWhitespace(character: string) {
  const code = character.charCodeAt(0)
  return /\p{White_Space}/u.test(character) || (code >= 0x1c && code <= 0x1f)
}

export function termsFromTextarea(value: string) {
  return value
    .split(/\r?\n/u)
    .map(trimRuleValue)
    .filter((term) => term.length > 0)
}

export function normalizeForDuplicateCheck(value: string) {
  // Python's full Unicode casefold remains authoritative at save time.
  return trimRuleValue(
    trimRuleValue(value).normalize('NFKC').toLocaleLowerCase('zh-CN'),
  )
}

export function composeMonitoringTerms(objects: string[], issues: string[]) {
  const count = objects.length * Math.max(1, issues.length)
  // Do not allocate an oversized product or silently show a truncated preview.
  if (count > MAX_TERMS_PER_RULE) {
    return { count, terms: [] }
  }
  return {
    count,
    terms:
      issues.length === 0
        ? objects.map(trimRuleValue)
        : objects.flatMap((object) =>
            issues.map(
              (issue) => `${trimRuleValue(object)} ${trimRuleValue(issue)}`,
            ),
          ),
  }
}
