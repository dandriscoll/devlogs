package io.github.dandriscoll.devlogs;

import com.cloudbees.plugins.credentials.CredentialsProvider;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import hudson.Extension;
import hudson.console.ConsoleLogFilter;
import hudson.model.Run;
import hudson.model.TaskListener;
import okhttp3.*;
import org.jenkinsci.plugins.plaincredentials.StringCredentials;
import org.jenkinsci.plugins.workflow.steps.*;
import org.kohsuke.stapler.DataBoundConstructor;
import org.kohsuke.stapler.DataBoundSetter;

import javax.annotation.Nonnull;
import java.io.IOException;
import java.io.OutputStream;
import java.io.Serializable;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

/**
 * Pipeline step that wraps build execution and streams logs to a devlogs instance.
 *
 * Example usage in Jenkinsfile:
 * <pre>
 * // Using credentials ID (recommended):
 * devlogs(credentialsId: 'devlogs-opensearch-url') {
 *     sh 'make build'
 * }
 *
 * // Using direct URL (not recommended for production):
 * devlogs(url: 'https://admin:password@opensearch.example.com:9200/devlogs-myproject') {
 *     sh 'make build'
 * }
 * </pre>
 */
public class DevlogsStep extends Step implements Serializable {
    private static final long serialVersionUID = 1L;

    // Pattern to detect environment variable prefixes like "DEVLOGS_OPENSEARCH_URL="
    private static final Pattern ENV_PREFIX_PATTERN = Pattern.compile("^[A-Z][A-Z0-9_]*=");

    private String url;
    private String credentialsId;
    private String index;

    @DataBoundConstructor
    public DevlogsStep() {
        // Default constructor - url or credentialsId set via setters
    }

    public String getUrl() {
        return url;
    }

    @DataBoundSetter
    public void setUrl(String url) {
        this.url = url;
    }

    public String getCredentialsId() {
        return credentialsId;
    }

    @DataBoundSetter
    public void setCredentialsId(String credentialsId) {
        this.credentialsId = credentialsId;
    }

    public String getIndex() {
        return index;
    }

    @DataBoundSetter
    public void setIndex(String index) {
        this.index = index;
    }

    /**
     * Resolve the URL from either direct url parameter or credentialsId lookup.
     *
     * @param run The current build run for credential resolution
     * @return The resolved OpenSearch URL, or null if not configured
     */
    private String resolveUrl(Run<?, ?> run) {
        // Direct URL takes precedence
        if (url != null && !url.trim().isEmpty()) {
            return url;
        }

        // Look up credentialsId
        if (credentialsId != null && !credentialsId.trim().isEmpty()) {
            StringCredentials creds = CredentialsProvider.findCredentialById(
                credentialsId,
                StringCredentials.class,
                run
            );
            if (creds != null) {
                return creds.getSecret().getPlainText();
            }
        }

        return null;
    }

    @Override
    public StepExecution start(StepContext context) throws Exception {
        Run<?, ?> run = context.get(Run.class);
        String resolvedUrl = resolveUrl(run);
        return new DevlogsStepExecution(context, resolvedUrl, index, credentialsId);
    }

    @Extension
    public static class DescriptorImpl extends StepDescriptor {

        @Override
        public String getFunctionName() {
            return "devlogs";
        }

        @Nonnull
        @Override
        public String getDisplayName() {
            return "Stream logs to Devlogs";
        }

        @Override
        public boolean takesImplicitBlockArgument() {
            return true;
        }

        @Override
        public Set<? extends Class<?>> getRequiredContext() {
            return Set.of(Run.class, TaskListener.class);
        }
    }

    /**
     * Validates the URL and returns an error message if invalid, or null if valid.
     */
    private static String validateUrl(String url) {
        if (url == null || url.trim().isEmpty()) {
            return null; // Handled separately as missing URL
        }

        String trimmedUrl = url.trim();

        // Check for environment variable prefix (e.g., "DEVLOGS_OPENSEARCH_URL=https://...")
        if (ENV_PREFIX_PATTERN.matcher(trimmedUrl).find()) {
            int equalsPos = trimmedUrl.indexOf('=');
            String prefix = trimmedUrl.substring(0, equalsPos);
            return "URL contains an environment variable prefix '" + prefix + "='. " +
                   "The credential should contain only the URL value, not the variable assignment. " +
                   "Remove the '" + prefix + "=' prefix from your credential.";
        }

        // Check for valid scheme
        if (!trimmedUrl.startsWith("http://") && !trimmedUrl.startsWith("https://")) {
            if (trimmedUrl.contains("://")) {
                String scheme = trimmedUrl.substring(0, trimmedUrl.indexOf("://"));
                return "URL has unsupported scheme '" + scheme + "'. Only 'http' and 'https' are supported.";
            } else {
                return "URL is missing the scheme. Expected format: https://user:pass@host:port/index";
            }
        }

        // Try to parse as URI to validate structure
        try {
            URI uri = new URI(trimmedUrl);
            if (uri.getHost() == null || uri.getHost().isEmpty()) {
                return "URL is missing a host. Expected format: https://user:pass@host:port/index";
            }
        } catch (URISyntaxException e) {
            return "URL is malformed: " + e.getMessage();
        }

        return null; // Valid
    }

    /**
     * Execution for the devlogs step.
     */
    public static class DevlogsStepExecution extends AbstractStepExecutionImpl {
        private static final long serialVersionUID = 1L;

        private final String url;
        private final String index;
        private final String credentialsId;
        private transient DevlogsConsoleLogFilter filter;

        public DevlogsStepExecution(StepContext context, String url, String index, String credentialsId) {
            super(context);
            this.url = url;
            this.index = index;
            this.credentialsId = credentialsId;
        }

        private void consoleLog(String message) {
            try {
                TaskListener listener = getContext().get(TaskListener.class);
                if (listener != null) {
                    listener.getLogger().println("[devlogs] " + message);
                }
            } catch (Exception e) {
                // Ignore - can't log to console
            }
        }

        @Override
        public boolean start() throws Exception {
            // Check if URL is missing
            if (url == null || url.trim().isEmpty()) {
                String credInfo = (credentialsId != null && !credentialsId.isEmpty())
                    ? "Credential '" + credentialsId + "' not found or empty."
                    : "No credentialsId or url parameter provided.";
                consoleLog("WARNING: " + credInfo + " Devlogs disabled for this build.");
                getContext().newBodyInvoker().withCallback(BodyExecutionCallback.wrap(getContext())).start();
                return false;
            }

            // Validate URL format
            String validationError = validateUrl(url);
            if (validationError != null) {
                consoleLog("ERROR: " + validationError);
                consoleLog("Devlogs disabled for this build.");
                getContext().newBodyInvoker().withCallback(BodyExecutionCallback.wrap(getContext())).start();
                return false;
            }

            Run<?, ?> run = getContext().get(Run.class);
            if (run == null) {
                throw new IllegalStateException("Run context is not available");
            }

            // Extract index name for logging
            String indexName = index;
            if (indexName == null || indexName.trim().isEmpty()) {
                int lastSlash = url.lastIndexOf('/');
                if (lastSlash > 0 && lastSlash < url.length() - 1) {
                    indexName = url.substring(lastSlash + 1);
                } else {
                    indexName = "devlogs";
                }
            }
            consoleLog("Streaming logs to OpenSearch index '" + indexName + "'");

            // Create and register the log filter
            filter = new DevlogsConsoleLogFilter(url, index, run);

            getContext().newBodyInvoker()
                .withContext(BodyInvoker.mergeConsoleLogFilters(getContext().get(ConsoleLogFilter.class), filter))
                .withCallback(BodyExecutionCallback.wrap(getContext()))
                .start();

            return false;
        }

        @Override
        public void stop(@Nonnull Throwable cause) throws Exception {
            if (filter != null) {
                filter.close();
            }
            getContext().onFailure(cause);
        }
    }

    /**
     * Console log filter that intercepts and streams logs to devlogs.
     */
    private static class DevlogsConsoleLogFilter extends ConsoleLogFilter implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String url;
        private final String index;
        private final String runId;
        private final String jobName;
        private final int buildNumber;
        private final String buildUrl;
        private final AtomicInteger seq = new AtomicInteger(0);

        public DevlogsConsoleLogFilter(String url, String index, Run<?, ?> run) {
            this.url = url;

            // Extract index from URL if not provided separately
            if (index == null || index.trim().isEmpty()) {
                this.index = extractIndexFromUrl(url);
            } else {
                this.index = index;
            }

            this.runId = run.getExternalizableId();
            this.jobName = run.getParent().getFullName();
            this.buildNumber = run.getNumber();
            this.buildUrl = run.getUrl();
        }

        private String extractIndexFromUrl(String url) {
            try {
                int lastSlash = url.lastIndexOf('/');
                if (lastSlash > 0 && lastSlash < url.length() - 1) {
                    return url.substring(lastSlash + 1);
                }
            } catch (Exception e) {
                // Fall back to default
            }
            return "devlogs";
        }

        @Override
        public OutputStream decorateLogger(Run build, OutputStream logger) throws IOException, InterruptedException {
            return new DevlogsOutputStream(logger, url, index, runId, jobName, buildNumber, buildUrl, seq);
        }

        public void close() {
            // Cleanup if needed
        }
    }

    /**
     * OutputStream that captures log lines and sends them to devlogs.
     */
    private static class DevlogsOutputStream extends OutputStream implements Serializable {
        private static final long serialVersionUID = 1L;
        private static final int BUFFER_SIZE = 8192;
        private static final int BATCH_SIZE = 10;
        private static final long BATCH_TIMEOUT_MS = 10000; // 10 seconds

        private final OutputStream delegate;
        private final String baseUrl;
        private final String index;
        private final String runId;
        private final String jobName;
        private final int buildNumber;
        private final String buildUrl;
        private final AtomicInteger seq;

        private final byte[] buffer = new byte[BUFFER_SIZE];
        private int bufferPos = 0;
        private final StringBuilder lineBuffer = new StringBuilder();
        private final StringBuilder batchBuffer = new StringBuilder();
        private int batchCount = 0;
        private long lastBatchTime = System.currentTimeMillis();
        private String currentLineTimestamp = null;
        private final String authHeader;
        private boolean errorReported = false; // Only report first error to avoid spam

        private transient OkHttpClient client;
        private transient Gson gson;

        public DevlogsOutputStream(OutputStream delegate, String url, String index, String runId,
                                   String jobName, int buildNumber, String buildUrl, AtomicInteger seq) {
            this.delegate = delegate;
            this.index = index;
            this.runId = runId;
            this.jobName = jobName;
            this.buildNumber = buildNumber;
            this.buildUrl = buildUrl;
            this.seq = seq;

            // Parse URL to extract credentials and base URL
            String parsedBaseUrl = url;
            String parsedAuthHeader = null;

            try {
                URI uri = new URI(url);
                String userInfo = uri.getUserInfo();
                if (userInfo != null && !userInfo.isEmpty()) {
                    // Build auth header from credentials
                    parsedAuthHeader = "Basic " + Base64.getEncoder().encodeToString(
                        userInfo.getBytes(StandardCharsets.UTF_8));

                    // Rebuild URL without credentials
                    int port = uri.getPort();
                    String portStr = (port > 0) ? ":" + port : "";
                    String path = uri.getPath();
                    // Remove trailing path segment (index name)
                    if (path != null && path.lastIndexOf('/') > 0) {
                        path = path.substring(0, path.lastIndexOf('/'));
                    } else {
                        path = "";
                    }
                    parsedBaseUrl = uri.getScheme() + "://" + uri.getHost() + portStr + path;
                } else {
                    // No credentials in URL, extract base URL the simple way
                    int lastSlash = url.lastIndexOf('/');
                    if (lastSlash > 0) {
                        parsedBaseUrl = url.substring(0, lastSlash);
                    }
                }
            } catch (URISyntaxException e) {
                // Fall back to simple extraction
                int lastSlash = url.lastIndexOf('/');
                if (lastSlash > 0) {
                    parsedBaseUrl = url.substring(0, lastSlash);
                }
            }

            this.baseUrl = parsedBaseUrl;
            this.authHeader = parsedAuthHeader;

            initTransients();
        }

        private void initTransients() {
            if (client == null) {
                client = new OkHttpClient.Builder()
                    .followRedirects(true)
                    .followSslRedirects(true)
                    .build();
            }
            if (gson == null) {
                gson = new Gson();
            }
        }

        @Override
        public void write(int b) throws IOException {
            delegate.write(b);

            buffer[bufferPos++] = (byte) b;

            if (b == '\n' || bufferPos >= BUFFER_SIZE) {
                processBuffer();
            }
        }

        @Override
        public void write(byte[] b, int off, int len) throws IOException {
            delegate.write(b, off, len);

            for (int i = 0; i < len; i++) {
                buffer[bufferPos++] = b[off + i];

                if (b[off + i] == '\n' || bufferPos >= BUFFER_SIZE) {
                    processBuffer();
                }
            }
        }

        @Override
        public void flush() throws IOException {
            delegate.flush();
            if (bufferPos > 0) {
                processBuffer();
            }
            if (lineBuffer.length() > 0) {
                String timestamp = (currentLineTimestamp != null) ? currentLineTimestamp : Instant.now().toString();
                sendLine(lineBuffer.toString(), timestamp);
                lineBuffer.setLength(0);
                currentLineTimestamp = null;
            }
            flushBatch();
        }

        @Override
        public void close() throws IOException {
            flush();
            delegate.close();
        }

        private void processBuffer() {
            if (bufferPos == 0) return;

            String text = new String(buffer, 0, bufferPos, StandardCharsets.UTF_8);
            bufferPos = 0;

            for (char c : text.toCharArray()) {
                if (c == '\n') {
                    if (lineBuffer.length() > 0) {
                        String timestamp = (currentLineTimestamp != null) ? currentLineTimestamp : Instant.now().toString();
                        sendLine(lineBuffer.toString(), timestamp);
                        lineBuffer.setLength(0);
                        currentLineTimestamp = null;
                    }
                } else {
                    if (lineBuffer.length() == 0 && currentLineTimestamp == null) {
                        currentLineTimestamp = Instant.now().toString();
                    }
                    lineBuffer.append(c);
                }
            }
        }

        private void sendLine(String line, String timestamp) {
            if (line.trim().isEmpty()) return;

            try {
                initTransients();

                long currentTime = System.currentTimeMillis();
                if (batchCount > 0 && (currentTime - lastBatchTime) >= BATCH_TIMEOUT_MS) {
                    flushBatch();
                }

                JsonObject doc = new JsonObject();
                doc.addProperty("doc_type", "log_entry");
                doc.addProperty("timestamp", timestamp);
                doc.addProperty("run_id", runId);
                doc.addProperty("job", jobName);
                doc.addProperty("build_number", buildNumber);
                doc.addProperty("build_url", buildUrl);
                doc.addProperty("seq", seq.incrementAndGet());
                doc.addProperty("message", line);
                doc.addProperty("source", "jenkins");
                doc.addProperty("level", "info");

                batchBuffer.append("{\"index\":{\"_index\":\"").append(index).append("\"}}\n");
                batchBuffer.append(gson.toJson(doc)).append("\n");
                batchCount++;

                if (batchCount == 1) {
                    lastBatchTime = currentTime;
                }

                if (batchCount >= BATCH_SIZE) {
                    flushBatch();
                }
            } catch (Exception e) {
                // Don't fail the build if logging fails
            }
        }

        private void consoleError(String message) {
            if (errorReported) return; // Only report first error
            errorReported = true;
            try {
                String line = "[devlogs] " + message + "\n";
                delegate.write(line.getBytes(StandardCharsets.UTF_8));
                delegate.flush();
            } catch (IOException e) {
                // Can't write to console
            }
        }

        private void flushBatch() {
            if (batchCount == 0) return;

            try {
                initTransients();

                String bulkUrl = baseUrl + "/_bulk";

                RequestBody body = RequestBody.create(
                    batchBuffer.toString(),
                    MediaType.parse("application/x-ndjson")
                );

                Request.Builder requestBuilder = new Request.Builder()
                    .url(bulkUrl)
                    .post(body);

                if (authHeader != null) {
                    requestBuilder.addHeader("Authorization", authHeader);
                }

                Request request = requestBuilder.build();

                try (Response response = client.newCall(request).execute()) {
                    if (!response.isSuccessful()) {
                        String responseBody = response.body() != null ? response.body().string() : "";
                        String detail = responseBody.length() > 100 ? responseBody.substring(0, 100) + "..." : responseBody;
                        consoleError("ERROR: Failed to send logs to OpenSearch. HTTP " + response.code() + ": " + detail);
                    }
                }

                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            } catch (Exception e) {
                consoleError("ERROR: Failed to send logs to OpenSearch: " + e.getMessage());
                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            }
        }
    }
}
