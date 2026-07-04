import { http, HttpResponse } from 'msw'
import * as mockData from './data'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const handlers = [
  // Graph API
  http.get('/graphs', () => HttpResponse.json(mockData.knowledgeGraphResponse)),
  http.get('/graph/label/list', () => HttpResponse.json(mockData.graphLabelListResponse)),
  http.get('/graph/label/popular', () => HttpResponse.json(mockData.popularLabelsResponse)),
  http.get('/graph/label/search', () => HttpResponse.json(mockData.graphLabelListResponse.slice(0, 2))),
  http.get('/graph/entity/exists', () => HttpResponse.json(mockData.entityExistsResponse)),
  http.post('/graph/entity/edit', () => HttpResponse.json(mockData.entityUpdateResponse)),
  http.post('/graph/relation/edit', () => HttpResponse.json(mockData.docActionResponse)),

  // Documents API
  http.get('/documents', () => HttpResponse.json(mockData.allDocumentsResponse)),
  http.post('/documents/paginated', () => HttpResponse.json(mockData.paginatedDocsResponse)),
  http.get('/documents/status_counts', () => HttpResponse.json(mockData.statusCountsResponse)),
  http.post('/documents/scan', () => HttpResponse.json(mockData.scanResponse)),
  http.get('/documents/scan-progress', () => HttpResponse.json(mockData.scanProgressResponse)),
  http.post('/documents/reprocess_failed', () => HttpResponse.json(mockData.reprocessFailedResponse)),
  http.get('/documents/track_status/:trackId', () => HttpResponse.json(mockData.trackStatusResponse)),
  http.get('/documents/pipeline_status', () => HttpResponse.json(mockData.pipelineStatusResponse)),
  http.post('/documents/cancel_pipeline', () => HttpResponse.json(mockData.cancelPipelineResponse)),
  http.post('/documents/text', () => HttpResponse.json(mockData.docActionResponse)),
  http.post('/documents/texts', () => HttpResponse.json(mockData.docActionResponse)),
  http.post('/documents/upload', () => HttpResponse.json(mockData.uploadResponse)),
  http.delete('/documents', () => HttpResponse.json(mockData.docActionResponse)),
  http.delete('/documents/delete_document', () => HttpResponse.json(mockData.deleteDocumentsResponse)),
  http.post('/documents/clear_cache', () => HttpResponse.json(mockData.clearCacheResponse)),

  // Query API
  http.post('/query', () => HttpResponse.json(mockData.queryResponse)),
  http.post('/query/stream', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        const message = `
# Демонстрация всех элементов разметки

Этот ответ демонстрирует все возможности форматирования, поддерживаемые фронтендом.

---

## 1. Базовый Markdown

Это **жирный** текст, а это *курсив*. Можно и ~~зачеркнутый~~.

> Это цитата. Она используется для выделения важных мыслей или высказываний.

- Неупорядоченный список, элемент 1
- Неупорядоченный список, элемент 2
  - Вложенный элемент

1. Упорядоченный список, элемент 1
2. Упорядоченный список, элемент 2

## 2. Таблицы (GFM)

| Заголовок 1 | Заголовок 2 | Заголовок 3 |
|:-----------:|:----------- |------------:|
| Ячейка 1    | Ячейка 2    | Ячейка 3    |
| Ячейка 4    | Ячейка 5    | Ячейка 6    |

## 3. Списки задач

- [x] Изучить возможности рендерера
- [ ] Написать сложный мок-ответ
- [ ] Проверить отображение

## 4. Блоки кода с подсветкой

Вот пример кода на Python:
\`\`\`python
import numpy as np

def main():
    x = np.array([1, 2, 3])
    print(f"Hello from mock! Your vector is: {x}")

if __name__ == "__main__":
    main()
\`\`\`

## 5. Математические формулы (LaTeX)

Формула в тексте: $E = mc^2$.

Блочная формула:
$$
\\int_a^b f(x) dx = F(b) - F(a)
$$

И более сложная, химическая, с помощью \`mhchem\`:
$$
\\ce{Zn^2+  <=>[+ 2OH-][+ 2H+]  $\\underset{\\text{amphoteric hydroxide}}{\\ce{Zn(OH)2 v}}$  <=>[+ 2OH-][+ 2H+]  $\\underset{\\text{tetrahydroxozincate}}{\\ce{[Zn(OH)4]^2-}}$}
$$

## 6. Диаграммы Mermaid

\`\`\`mermaid
graph TD
    A[Начало] -->|Запрос| B(Обработка);
    B --> C{Решение};
    C -->|Да| D[Конец];
    C -->|Нет| E[Ошибка];
\`\`\`
`;
        const words = message.split(' ');

        for (const word of words) {
          const chunk = { response: `${word} ` };
          controller.enqueue(encoder.encode(JSON.stringify(chunk) + '\n'));
          await sleep(25); // a bit faster
        }

        controller.close();
      },
    });
    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'application/x-ndjson',
      },
    });
  }),

  // System & Auth API
  http.get('/health', () => HttpResponse.json(mockData.healthStatusResponse)),
  http.get('/auth-status', () => HttpResponse.json(mockData.authStatusResponse)),
  http.post('/login', () => HttpResponse.json(mockData.loginResponse)),
]
