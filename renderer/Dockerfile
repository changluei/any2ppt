# Playwright 基础镜像自带浏览器与系统字体依赖，供 Slidev 截图/导出使用。
FROM mcr.microsoft.com/playwright:v1.61.1-noble
WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# npm ci 固定 renderer 依赖版本；主题包在运行时写入持久化 theme cache。
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY server.mjs ./
CMD ["npm", "start"]
