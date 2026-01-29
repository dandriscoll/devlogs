package io.github.dandriscoll.devlogs;

import hudson.model.InvisibleAction;
import hudson.model.Run;

import java.io.Serializable;

/**
 * Invisible action that stores devlogs configuration for a build.
 * Used by DevlogsGlobalDecorator.Factory to determine if devlogs is enabled.
 */
public class DevlogsAction extends InvisibleAction implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String url;
    private final String index;
    private final String runId;
    private final String jobName;
    private final int buildNumber;
    private final String buildUrl;
    private final String application;
    private final String component;
    private final String environment;
    private final String version;
    private final boolean pipeline;

    public DevlogsAction(String url, String index, Run<?, ?> run,
                         String application, String component,
                         String environment, String version, boolean pipeline) {
        this.url = url;
        this.application = application;
        this.component = component;
        this.environment = environment;
        this.version = version;
        this.pipeline = pipeline;

        // Extract index from URL if not provided separately (for direct mode)
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
                String potential = url.substring(lastSlash + 1);
                // Don't treat API paths as index names
                if (!potential.startsWith("v1") && !potential.equals("logs")) {
                    return potential;
                }
            }
        } catch (Exception e) {
            // Fall back to default
        }
        return "devlogs";
    }

    public String getUrl() { return url; }
    public String getIndex() { return index; }
    public String getRunId() { return runId; }
    public String getJobName() { return jobName; }
    public int getBuildNumber() { return buildNumber; }
    public String getBuildUrl() { return buildUrl; }
    public String getApplication() { return application; }
    public String getComponent() { return component; }
    public String getEnvironment() { return environment; }
    public String getVersion() { return version; }
    public boolean isPipeline() { return pipeline; }
}
