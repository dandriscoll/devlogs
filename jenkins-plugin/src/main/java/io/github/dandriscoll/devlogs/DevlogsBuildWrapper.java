package io.github.dandriscoll.devlogs;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import hudson.EnvVars;
import hudson.Extension;
import hudson.FilePath;
import hudson.Launcher;
import hudson.console.ConsoleLogFilter;
import hudson.model.AbstractProject;
import hudson.model.Run;
import hudson.model.TaskListener;
import hudson.tasks.BuildWrapperDescriptor;
import jenkins.tasks.SimpleBuildWrapper;
import okhttp3.*;
import org.jenkinsci.Symbol;
import org.kohsuke.stapler.DataBoundConstructor;
import org.kohsuke.stapler.DataBoundSetter;

import javax.annotation.Nonnull;
import java.io.IOException;
import java.io.OutputStream;
import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Build wrapper that streams all console output to a devlogs instance.
 *
 * This can be used in declarative pipelines via the options block:
 * <pre>
 * pipeline {
 *     options {
 *         devlogs(url: 'https://admin:password@opensearch.example.com:9200/devlogs-myproject')
 *     }
 *     stages {
 *         stage('Build') {
 *             steps {
 *                 sh 'make build'  // automatically captured
 *             }
 *         }
 *     }
 * }
 * </pre>
 *
 * Or configured via the Jenkins UI on the job configuration page.
 */
public class DevlogsBuildWrapper extends SimpleBuildWrapper implements Serializable {
    private static final long serialVersionUID = 1L;

    private String url;
    private String index;

    @DataBoundConstructor
    public DevlogsBuildWrapper() {
        // Default constructor for UI configuration
    }

    public String getUrl() {
        return url;
    }

    @DataBoundSetter
    public void setUrl(String url) {
        this.url = url;
    }

    public String getIndex() {
        return index;
    }

    @DataBoundSetter
    public void setIndex(String index) {
        this.index = index;
    }

    @Override
    public void setUp(Context context, Run<?, ?> build, FilePath workspace,
                      Launcher launcher, TaskListener listener, EnvVars initialEnvironment)
            throws IOException, InterruptedException {
        // Resolve environment variables in URL
        String resolvedUrl = initialEnvironment.expand(url);

        if (resolvedUrl == null || resolvedUrl.trim().isEmpty()) {
            listener.getLogger().println("[Devlogs] No URL configured, skipping log streaming");
            return;
        }

        listener.getLogger().println("[Devlogs] Streaming logs to " + maskUrl(resolvedUrl));
    }

    @Override
    public ConsoleLogFilter createLoggerDecorator(@Nonnull Run<?, ?> build) {
        if (url == null || url.trim().isEmpty()) {
            return null;
        }
        return new DevlogsConsoleLogFilter(url, index, build);
    }

    /**
     * Mask credentials in URL for display
     */
    private String maskUrl(String url) {
        return url.replaceAll("://[^:]+:[^@]+@", "://****:****@");
    }

    @Extension
    @Symbol("devlogs")
    public static class DescriptorImpl extends BuildWrapperDescriptor {

        @Nonnull
        @Override
        public String getDisplayName() {
            return "Stream logs to Devlogs";
        }

        @Override
        public boolean isApplicable(AbstractProject<?, ?> item) {
            return true;
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

        @SuppressWarnings("rawtypes")
        @Override
        public OutputStream decorateLogger(Run build, OutputStream logger)
                throws IOException, InterruptedException {
            return new DevlogsOutputStream(logger, url, index, runId, jobName, buildNumber, buildUrl, seq);
        }
    }

    /**
     * OutputStream that captures log lines and sends them to devlogs.
     */
    private static class DevlogsOutputStream extends OutputStream implements Serializable {
        private static final long serialVersionUID = 1L;
        private static final int BUFFER_SIZE = 8192;
        private static final int BATCH_SIZE = 10;
        private static final long BATCH_TIMEOUT_MS = 10000;

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

            // Extract base URL (without index)
            int lastSlash = url.lastIndexOf('/');
            if (lastSlash > 0) {
                this.baseUrl = url.substring(0, lastSlash);
            } else {
                this.baseUrl = url;
            }

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
                System.err.println("Warning: Failed to send log to devlogs: " + e.getMessage());
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

                Request request = new Request.Builder()
                    .url(bulkUrl)
                    .post(body)
                    .build();

                try (Response response = client.newCall(request).execute()) {
                    if (!response.isSuccessful()) {
                        System.err.println("Warning: Devlogs bulk request failed: " + response.code());
                    }
                }

                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            } catch (Exception e) {
                System.err.println("Warning: Failed to flush logs to devlogs: " + e.getMessage());
                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            }
        }
    }
}
