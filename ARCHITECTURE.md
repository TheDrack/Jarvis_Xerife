# 🏗️ JARVIS_Xerife: Mapa de Arquitetura Dinâmico
> **Protocolo de Simbiose:** Documentação gerada via análise de código real.

```mermaid
graph LR
    classDef core fill:#1a1f25,stroke:#00ff00,color:#fff,stroke-width:2px;
    classDef adapter fill:#1a1f25,stroke:#007bff,color:#fff;
    classDef port fill:#1a1f25,stroke:#ffa500,color:#fff,stroke-dasharray: 5 5;
    classDef support fill:#2d333b,stroke:#6c757d,color:#aaa;
    migrations["<b>migrations</b>"]
    class migrations support
    requirements["<b>requirements</b>"]
    class requirements support
    config["<b>config</b>"]
    class config support
    config_pipelines["<b>pipelines</b>"]
    class config_pipelines support
    config --> config_pipelines
    _backups["<b>.backups</b>"]
    class _backups support
    _backups_cleanup["<b>cleanup</b>"]
    class _backups_cleanup support
    _backups --> _backups_cleanup
    _backups_nexus_20260310_160218["<b>nexus_20260310_160218</b>"]
    class _backups_nexus_20260310_160218 support
    _backups --> _backups_nexus_20260310_160218
    _backups_nexus_20260310_160218_app["<b>app</b>"]
    class _backups_nexus_20260310_160218_app support
    _backups_nexus_20260310_160218 --> _backups_nexus_20260310_160218_app
    _backups_nexus_20260310_160218_app_adapters["<b>adapters</b>"]
    class _backups_nexus_20260310_160218_app_adapters adapter
    _backups_nexus_20260310_160218_app --> _backups_nexus_20260310_160218_app_adapters
    _backups_nexus_20260310_160218_app_adapters_infrastructure["<b>infrastructure</b><br/><hr/>📄 github_adapter.py: GitHubAdapter, execute<br/>📄 gateway_llm_adapter.py: GatewayLLMCommandAdapter, get_system_instruction<br/>📄 api_server.py: get_current_user, create_api_server, telegram_webhook"]
    class _backups_nexus_20260310_160218_app_adapters_infrastructure adapter
    _backups_nexus_20260310_160218_app_adapters --> _backups_nexus_20260310_160218_app_adapters_infrastructure
    _backups_nexus_20260310_160218_app_adapters_infrastructure_routers["<b>routers</b><br/><hr/>📄 evolution.py: create_evolution_router, get_evolution_status<br/>📄 github.py: create_github_router, github_worker_operation, auto_heal_ci_failure"]
    class _backups_nexus_20260310_160218_app_adapters_infrastructure_routers adapter
    _backups_nexus_20260310_160218_app_adapters_infrastructure --> _backups_nexus_20260310_160218_app_adapters_infrastructure_routers
    _backups_nexus_20260310_160218_app_adapters_edge["<b>edge</b><br/><hr/>📄 worker_pc.py: main"]
    class _backups_nexus_20260310_160218_app_adapters_edge adapter
    _backups_nexus_20260310_160218_app_adapters --> _backups_nexus_20260310_160218_app_adapters_edge
    _backups_nexus_20260310_160218_app_application["<b>application</b>"]
    class _backups_nexus_20260310_160218_app_application support
    _backups_nexus_20260310_160218_app --> _backups_nexus_20260310_160218_app_application
    _backups_nexus_20260310_160218_app_application_services["<b>services</b><br/><hr/>📄 assistant_service.py: AssistantService<br/>📄 capability_gap_reporter.py: CapabilityGapReporter, execute"]
    class _backups_nexus_20260310_160218_app_application_services support
    _backups_nexus_20260310_160218_app_application --> _backups_nexus_20260310_160218_app_application_services
    capabilities["<b>capabilities</b><br/><hr/>📄 classification.py: from, CapabilityStatus, class"]
    class capabilities support
    mobile["<b>mobile</b>"]
    class mobile support
    mobile_android["<b>android</b>"]
    class mobile_android support
    mobile --> mobile_android
    mobile_android_app["<b>app</b>"]
    class mobile_android_app support
    mobile_android --> mobile_android_app
    mobile_android_app_src["<b>src</b>"]
    class mobile_android_app_src support
    mobile_android_app --> mobile_android_app_src
    mobile_android_app_src_main["<b>main</b>"]
    class mobile_android_app_src_main support
    mobile_android_app_src --> mobile_android_app_src_main
    mobile_android_app_src_main_java["<b>java</b>"]
    class mobile_android_app_src_main_java support
    mobile_android_app_src_main --> mobile_android_app_src_main_java
    mobile_android_app_src_main_java_com["<b>com</b>"]
    class mobile_android_app_src_main_java_com support
    mobile_android_app_src_main_java --> mobile_android_app_src_main_java_com
    mobile_android_app_src_main_java_com_thedrack["<b>thedrack</b>"]
    class mobile_android_app_src_main_java_com_thedrack support
    mobile_android_app_src_main_java_com --> mobile_android_app_src_main_java_com_thedrack
    mobile_android_app_src_main_java_com_thedrack_jarvismobile["<b>jarvismobile</b>"]
    class mobile_android_app_src_main_java_com_thedrack_jarvismobile support
    mobile_android_app_src_main_java_com_thedrack --> mobile_android_app_src_main_java_com_thedrack_jarvismobile
    skills["<b>skills</b>"]
    class skills support
    skills_jarvis-android-navigation["<b>jarvis-android-navigation</b>"]
    class skills_jarvis-android-navigation support
    skills --> skills_jarvis-android-navigation
    skills_jarvis-visual-navigation["<b>jarvis-visual-navigation</b>"]
    class skills_jarvis-visual-navigation support
    skills --> skills_jarvis-visual-navigation
    skills_jarvis-multi-agent-coordination["<b>jarvis-multi-agent-coordination</b>"]
    class skills_jarvis-multi-agent-coordination support
    skills --> skills_jarvis-multi-agent-coordination
    skills_jarvis-context-memory["<b>jarvis-context-memory</b>"]
    class skills_jarvis-context-memory support
    skills --> skills_jarvis-context-memory
    static["<b>static</b>"]
    class static support
    backups["<b>backups</b>"]
    class backups support
    app["<b>app</b><br/><hr/>📄 container.py: Container<br/>📄 bootstrap_edge.py: main"]
    class app support
    app_multiagent["<b>multiagent</b><br/><hr/>📄 supabase_queue.py: SupabaseQueueConnector, send<br/>📄 worker.py: AcknowledgingConnector, send, receive<br/>📄 supabase_store.py: SupabaseAgentStore, register_agent<br/>📄 transport.py: AgentMessage, create, to_dict<br/>📄 scheduler.py: from, NoEligibleAgentError, CostBenefitScheduler<br/>📄 freellmapi_client.py: FreeLLMAPIError, FreeLLMAPIClient<br/>📄 freellmapi_handler.py: FreeLLMAgentHandler<br/>📄 leader.py: from, class, AgentLeader<br/>📄 contracts.py: TaskStatus, AgentProfile<br/>📄 priority_queue_mini_agent.py: PriorityQueueMiniAgent, from_env"]
    class app_multiagent support
    app --> app_multiagent
    app_domain["<b>domain</b>"]
    class app_domain support
    app --> app_domain
    app_domain_context["<b>context</b><br/><hr/>📄 context_manager.py: SystemContext, ContextManager"]
    class app_domain_context support
    app_domain --> app_domain_context
    app_domain_ports["<b>ports</b><br/><hr/>📄 device_control_port.py: from, class, DeviceControlPort"]
    class app_domain_ports port
    app_domain --> app_domain_ports
    app_domain_capabilities["<b>capabilities</b><br/><hr/>📄 cap_053.py: Cap053, execute<br/>📄 cap_082.py: Cap082, execute<br/>📄 cap_102.py: Cap102, execute<br/>📄 cap_066.py: Cap066, execute<br/>📄 cap_079.py: Cap079, execute<br/>📄 cap_086.py: Cap086, execute<br/>📄 cap_009.py: Cap009, execute<br/>📄 cap_064.py: Cap064, execute<br/>📄 cap_006.py: Cap006, configure<br/>📄 cap_055.py: Cap055, execute<br/>📄 cap_058.py: Cap058, execute<br/>📄 cap_084.py: Cap084, execute<br/>📄 cap_010.py: Cap010, execute<br/>📄 cap_070.py: Cap070, execute<br/>📄 cap_007.py: Cap007, configure<br/>📄 cap_089.py: Cap089, execute<br/>📄 cap_094.py: Cap094, execute<br/>📄 cap_050.py: Cap050, execute<br/>📄 cap_057.py: Cap057, configure<br/>📄 cap_004.py: Cap004, configure<br/>📄 cap_056.py: Cap056, execute<br/>📄 cap_063.py: Cap063, execute<br/>📄 cap_080.py: Cap080, execute<br/>📄 cap_036.py: Cap036, execute<br/>📄 cap_078.py: Cap078, execute<br/>📄 cap_031.py: Cap031, execute<br/>📄 cap_090.py: Cap090, execute<br/>📄 cap_048.py: Cap048, execute<br/>📄 cap_045.py: Cap045, configure<br/>📄 cap_051.py: Cap051, execute<br/>📄 cap_022.py: Cap022, execute<br/>📄 cap_098.py: Cap098, execute<br/>📄 cap_083.py: Cap083, execute<br/>📄 cap_043.py: Cap043, execute<br/>📄 cap_039.py: Cap039, configure<br/>📄 cap_075.py: Cap075, execute<br/>📄 cap_100.py: Cap100, configure<br/>📄 cap_005.py: Cap005, configure<br/>📄 cap_062.py: Cap062, execute<br/>📄 cap_001.py: Cap001, configure<br/>📄 cap_065.py: Cap065, execute<br/>📄 cap_052.py: Cap052, execute<br/>📄 cap_020.py: Cap020, execute<br/>📄 cap_026.py: Cap026, execute<br/>📄 cap_024.py: Cap024, execute<br/>📄 cap_068.py: Cap068, execute<br/>📄 cap_046.py: Cap046, execute<br/>📄 cap_023.py: Cap023, configure<br/>📄 cap_018.py: Cap018, execute<br/>📄 cap_061.py: Cap061, execute<br/>📄 cap_092.py: Cap092, execute<br/>📄 cap_093.py: Cap093, execute<br/>📄 cap_030.py: Cap030, execute<br/>📄 cap_073.py: Cap073, execute<br/>📄 cap_069.py: Cap069, execute<br/>📄 cap_091.py: Cap091, execute<br/>📄 cap_016.py: Cap016, execute<br/>📄 cap_040.py: Cap040, configure<br/>📄 cap_028.py: Cap028, execute<br/>📄 cap_099.py: Cap099, execute<br/>📄 cap_033.py: Cap033, configure<br/>📄 cap_095.py: Cap095, configure<br/>📄 cap_101.py: Cap101, execute<br/>📄 cap_002.py: Cap002, configure<br/>📄 cap_087.py: Cap087, execute<br/>📄 context_memory.py: ContextMemory, configure, execute<br/>📄 cap_041.py: Cap041, execute<br/>📄 cap_077.py: Cap077, execute<br/>📄 cap_021.py: Cap021, execute<br/>📄 cap_081.py: Cap081, execute<br/>📄 cap_044.py: Cap044, configure<br/>📄 cap_054.py: Cap054, execute<br/>📄 cap_013.py: Cap013, execute<br/>📄 cap_059.py: Cap059, configure<br/>📄 cap_047.py: Cap047, configure<br/>📄 cap_038.py: Cap038, execute<br/>📄 cap_071.py: Cap071, execute<br/>📄 cap_027.py: Cap027, configure<br/>📄 cap_067.py: Cap067, configure<br/>📄 cap_085.py: Cap085, execute<br/>📄 cap_037.py: Cap037, execute<br/>📄 cap_096.py: Cap096, execute<br/>📄 cap_025.py: Cap025, execute<br/>📄 cap_015.py: Cap015, execute<br/>📄 cap_011.py: Cap011, execute<br/>📄 cap_032.py: Cap032, configure<br/>📄 cap_060.py: Cap060, execute<br/>📄 cap_097.py: Cap097, execute<br/>📄 cap_003.py: Cap003, configure<br/>📄 cap_049.py: Cap049, execute<br/>📄 cap_008.py: Cap008, configure<br/>📄 cap_076.py: Cap076, execute<br/>📄 cap_019.py: Cap019, execute<br/>📄 cap_035.py: Cap035, execute<br/>📄 cap_012.py: Cap012, execute<br/>📄 cap_029.py: Cap029, execute<br/>📄 cap_014.py: Cap014, execute<br/>📄 cap_042.py: Cap042, execute<br/>📄 cap_034.py: Cap034, configure<br/>📄 cap_072.py: Cap072, configure<br/>📄 cap_088.py: Cap088, execute<br/>📄 cap_074.py: Cap074, execute<br/>📄 cap_017.py: Cap017, execute"]
    class app_domain_capabilities support
    app_domain --> app_domain_capabilities
    app_domain_models["<b>models</b><br/><hr/>📄 system_state.py: SystemStatus, execute, Config<br/>📄 agent.py: ActionType, TaskSource, TaskPriority<br/>📄 thought_log.py: InteractionStatus, ThoughtLog, Config<br/>📄 adapter_registry.py: class, to_dict, AdapterRegistry<br/>📄 device.py: Device, execute, Capability<br/>📄 capability.py: JarvisCapability, execute<br/>📄 command.py: CommandType, Intent<br/>📄 evolution_reward.py: EvolutionReward, execute<br/>📄 viability.py: RiskLevel, ImpactLevel, class<br/>📄 soldier.py: SoldierStatus, SoldierRegistration, soldier_id_not_empty<br/>📄 mission.py: class, execute, to_dict"]
    class app_domain_models support
    app_domain --> app_domain_models
    app_domain_memory["<b>memory</b><br/><hr/>📄 prospective_memory.py: ProspectiveMemory<br/>📄 semantic_memory.py: SemanticMemory, configure<br/>📄 working_memory.py: WorkingMemoryEntry, WorkingMemory"]
    class app_domain_memory support
    app_domain --> app_domain_memory
    app_domain_ai["<b>ai</b><br/><hr/>📄 gemini_service.py: GeminiService, execute"]
    class app_domain_ai support
    app_domain --> app_domain_ai
    app_domain_services["<b>services</b><br/><hr/>📄 llm_command_interpreter.py: LLMCommandInterpreter, execute<br/>📄 command_interpreter.py: CommandInterpreter, execute<br/>📄 reward_signal_provider.py: record<br/>📄 agent_service.py: AgentService, execute<br/>📄 vocal_orchestrator.py: VocalOrchestrator, execute<br/>📄 system_state_tracker.py: SystemStateTracker, execute<br/>📄 intent_processor.py: IntentProcessor, can_execute, execute<br/>📄 safety_guardian.py: SafetyGuardian, configure<br/>📄 soldier_shield.py: SoldierShield, execute<br/>📄 state_manager.py: StateManager, execute"]
    class app_domain_services support
    app_domain --> app_domain_services
    app_domain_gears["<b>gears</b><br/><hr/>📄 llm_engine.py: LlmEngine, configure<br/>📄 cognitive_router.py: CognitiveRouter, configure"]
    class app_domain_gears support
    app_domain --> app_domain_gears
    app_domain_analysis["<b>analysis</b><br/><hr/>📄 performance_analyzer.py: PerformanceAnalyzer, execute"]
    class app_domain_analysis support
    app_domain --> app_domain_analysis
    app_domain_orchestration["<b>orchestration</b><br/><hr/>📄 central_orchestrator.py: CentralOrchestrator, execute"]
    class app_domain_orchestration support
    app_domain --> app_domain_orchestration
    app_domain_missions["<b>missions</b><br/><hr/>📄 mission_selector.py: MissionSelector, execute"]
    class app_domain_missions support
    app_domain --> app_domain_missions
    app_ports["<b>ports</b><br/><hr/>📄 secrets_provider.py: SecretsProvider, get_secret<br/>📄 voice_port.py: VoicePort, stt, tts"]
    class app_ports port
    app --> app_ports
    app_adapters["<b>adapters</b><br/><hr/>📄 jarvis_return_activity.py: LASTINPUTINFO, get_idle_seconds"]
    class app_adapters adapter
    app --> app_adapters
    app_adapters_infrastructure["<b>infrastructure</b><br/><hr/>📄 vision_adapter.py: ExternalVisionNotAllowedError, VisionAdapter<br/>📄 http_client.py: HttpClient<br/>📄 github_issue_adapter.py: GitHubIssueAdapter, execute<br/>📄 telegram_adapter.py: TelegramAdapter<br/>📄 gemini_context_manager.py: GeminiContextManager, execute<br/>📄 firebase_push.py: FirebasePushNotConfigured, FirebasePushDeliveryError<br/>📄 gemini_adapter.py: LLMCommandAdapter, execute<br/>📄 docker_sandbox.py: DockerSandbox, run_tests<br/>📄 github_adapter.py: GitHubAdapter, execute<br/>📄 auth_adapter.py: AuthAdapter, execute<br/>📄 reward_logger.py: RewardLogger, execute<br/>📄 audit_logger.py: AuditLogger, configure, execute<br/>📄 github_correction_adapter.py: GitHubCorrectionAdapter<br/>📄 socket_client.py: SocketClient, execute<br/>📄 dummy_voice_provider.py: DummyVoiceProvider, execute<br/>📄 setup_wizard.py: Colors, execute, print_header<br/>📄 mqtt_home_adapter.py: MqttHomeAdapter, execute<br/>📄 gist_uploader.py: GistUploader, execute<br/>📄 soldier_bridge.py: SoldierBridgeManager, connect<br/>📄 action_provider.py: ActionProvider, execute<br/>📄 gateway_llm_adapter.py: GatewayLLMCommandAdapter, get_system_instruction<br/>📄 auto_repair_mixin.py: AutoRepairMixin, must, execute<br/>📄 gemini_response_helpers.py: build_context_message, build_parameters, convert_function_call_to_intent<br/>📄 github_workflow_adapter.py: GitHubWorkflowAdapter, execute<br/>📄 websocket_manager.py: WebSocketManager, execute<br/>📄 overwatch_adapter.py: OverwatchDaemon, execute<br/>📄 ai_gateway_token_utils.py: count_tokens, TokenCounter<br/>📄 ollama_adapter.py: OllamaAdapter, configure<br/>📄 ai_gateway.py: AIGateway, groq_model<br/>📄 cost_tracker_adapter.py: CostTrackerAdapter<br/>📄 consolidator.py: NexusComponent, Consolidator<br/>📄 copilot_context_provider.py: GitHubCopilotContextProvider, execute, analyzes<br/>📄 sqlite_history_adapter.py: CoercingUTCDateTime, process_bind_param<br/>📄 github_issue_mixin.py: GitHubIssueMixin, provides, execute<br/>📄 system_executor.py: SystemExecutor, configure, can_execute<br/>📄 drive_uploader.py: DriveUploader, configure<br/>📄 persistent_shell_adapter.py: PersistentShellAdapter, configure<br/>📄 ai_gateway_enums.py: LLMProvider, GroqGear, AIGatewayEnums<br/>📄 pyinstaller_builder.py: PyinstallerBuilder, configure, can_execute<br/>📄 api_server.py: get_current_user, create_api_server, telegram_webhook<br/>📄 supabase_client.py: get_supabase_client, is_supabase_available, get_supabase_admin_client<br/>📄 api_models.py: RequestSource, RequestMetadata, ExecuteRequest<br/>📄 reward_adapter.py: RewardAdapter, execute<br/>📄 playwright_worker.py: PlaywrightWorker, start<br/>📄 jrvs_cloud_storage.py: JrvsCloudStorage, execute"]
    class app_adapters_infrastructure adapter
    app_adapters --> app_adapters_infrastructure
    app_adapters_infrastructure_osint["<b>osint</b><br/><hr/>📄 eagle_osint_adapter.py: EagleOsintAdapter"]
    class app_adapters_infrastructure_osint adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_osint
    app_adapters_infrastructure_secrets["<b>secrets</b><br/><hr/>📄 env_secrets_provider.py: EnvSecretsProvider, execute, get_secret"]
    class app_adapters_infrastructure_secrets adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_secrets
    app_adapters_infrastructure_routers["<b>routers</b><br/><hr/>📄 utility.py: create_utility_router, get_api_key_guides, analyze_missing_resources<br/>📄 devices.py: create_devices_router, register_device<br/>📄 agent_tasks.py: AgentHeartbeatRequest, EnqueueTaskRequest, ClaimTaskRequest<br/>📄 health.py: create_health_router, health_check, health_detail<br/>📄 extensions.py: create_extensions_router, install_package, get_package_status<br/>📄 dev_agent.py: create_dev_agent_router, run_dev_agent, list_dev_agent_jobs<br/>📄 mobile_sessions.py: MobileLoginRequest, MobileRefreshRequest, MobileRevokeRequest<br/>📄 evolution.py: create_evolution_router, get_evolution_status<br/>📄 assistant.py: create_assistant_router<br/>📄 thoughts.py: create_thoughts_router, create_thought_log<br/>📄 github.py: create_github_router, github_worker_operation, auto_heal_ci_failure<br/>📄 missions.py: create_missions_router, execute_mission, control_browser<br/>📄 admin_recovery.py: AdminPasswordResetRequest, create_admin_recovery_router<br/>📄 mobile_push.py: MobilePushRegistration, MobilePushRevoke, MobilePushStorageUnavailable<br/>📄 bridge.py: create_bridge_router, require_authenticated_principal, local_bridge_websocket"]
    class app_adapters_infrastructure_routers adapter
    app_adapters_infrastructure --> app_adapters_infrastructure_routers
    app_adapters_api["<b>api</b><br/><hr/>📄 voice_endpoint.py: voice_stream"]
    class app_adapters_api adapter
    app_adapters --> app_adapters_api
    app_adapters_edge["<b>edge</b><br/><hr/>📄 web_adapter.py: WebAdapter, execute<br/>📄 security_audit_adapter.py: TacticalCommandPort, NearbyDevice<br/>📄 voice_engine.py: JarvisEngine, execute<br/>📄 tts_adapter.py: TTSAdapter, execute<br/>📄 background_window_input.py: pack_point, click_window_background, enum_callback<br/>📄 jarvis_local_agent.py: JarvisLocalAgent, execute<br/>📄 worker_pc.py: main<br/>📄 android_navigation_adapter.py: AndroidNavigationAdapter<br/>📄 macrodroid_adapter.py: MacroDroidAdapter, can_execute<br/>📄 active_recruiter_adapter.py: ActiveRecruiterAdapter, execute<br/>📄 combined_voice_provider.py: CombinedVoiceProvider, execute<br/>📄 keyboard_adapter.py: KeyboardAdapter, execute, type_text<br/>📄 jarvis_desktop_mcp.py: curiosity_capture, curiosity_list_recent<br/>📄 hardware_controller.py: HardwareController, execute<br/>📄 automation_adapter.py: AutomationAdapter, execute<br/>📄 voice_adapter.py: VoiceAdapter, execute"]
    class app_adapters_edge adapter
    app_adapters --> app_adapters_edge
    app_runtime["<b>runtime</b><br/><hr/>📄 pipeline_runner.py: CloudMock, run_pipeline"]
    class app_runtime support
    app --> app_runtime
    app_core["<b>core</b><br/><hr/>📄 nexus_discovery.py: finders<br/>📄 llm_config.py: LLMConfig, use_llm_command_interpretation, use_llm_capability_detection<br/>📄 recovery_store.py: RecoveryError<br/>📄 nexus_exceptions.py: ImportTimeoutError, InstantiateTimeoutError, instantiation<br/>📄 encryption.py: get_hardware_id, derive_key_from_hardware, encrypt_value<br/>📄 nexus.py: JarvisNexus<br/>📄 config.py: Settings, decrypt_api_key, decrypt_database_url<br/>📄 nexuscomponent.py: NexusComponent"]
    class app_core core
    app --> app_core
    app_core_meta["<b>meta</b><br/><hr/>📄 decision_engine.py: class, DecisionEngine<br/>📄 exploration_controller.py: ExplorationController, execute<br/>📄 compile_lock.py: acquire_compile_lock<br/>📄 policy_store.py: PolicyStore, get_policies_by_module<br/>📄 jrvs_compiler.py: SchemaVersionError, JRVSCompiler"]
    class app_core_meta core
    app_core --> app_core_meta
    app_static["<b>static</b>"]
    class app_static support
    app --> app_static
    app_plugins["<b>plugins</b><br/><hr/>📄 plugin_loader.py: PluginLoader, execute"]
    class app_plugins support
    app --> app_plugins
    app_plugins_dynamic["<b>dynamic</b><br/><hr/>📄 example_plugin.py: hello_jarvis, register, PluginCapability"]
    class app_plugins_dynamic support
    app_plugins --> app_plugins_dynamic
    app_application["<b>application</b><br/><hr/>📄 return_activity_service.py: class, was_idle"]
    class app_application support
    app --> app_application
    app_application_privacy["<b>privacy</b><br/><hr/>📄 pii_redactor.py: PiiRedactor, execute"]
    class app_application_privacy support
    app_application --> app_application_privacy
    app_application_ports["<b>ports</b><br/><hr/>📄 web_provider.py: WebProvider, execute, open_url<br/>📄 soldier_provider.py: SoldierProvider, execute, register_soldier<br/>📄 visual_navigation.py: VisualNavigationPort, execute<br/>📄 memory_provider.py: MemoryProvider, execute, store_event<br/>📄 system_controller.py: SystemController, execute_command, is_available<br/>📄 tactical_command_port.py: TacticalCommandPort, execute, execute_security_payload<br/>📄 android_navigation.py: AndroidNavigationPort, observe_screen, tap<br/>📄 action_provider.py: ActionProvider, execute, type_text<br/>📄 security_provider.py: SecurityProvider, execute, verify_password<br/>📄 voice_provider.py: VoiceProvider, execute, speak<br/>📄 osint_provider.py: OsintProvider, search<br/>📄 reward_provider.py: RewardProvider, execute, log_reward<br/>📄 history_provider.py: HistoryProvider, execute, save_interaction"]
    class app_application_ports port
    app_application --> app_application_ports
    app_application_security["<b>security</b><br/><hr/>📄 capability_authorizer.py: CapabilityAuthorizer, can_execute"]
    class app_application_security support
    app_application --> app_application_security
    app_application_services["<b>services</b><br/><hr/>📄 surgical_edit_service.py: SurgicalEditService, apply_surgical_edit<br/>📄 tactical_map_service.py: TacticalMapService, execute<br/>📄 assistant_service.py: AssistantService<br/>📄 llm_capability_detector.py: LLMCapabilityDetector, execute<br/>📄 interface_bridge.py: InterfaceBridge, execute<br/>📄 notification_service.py: NotificationService, execute<br/>📄 consolidated_context_service.py: ConsolidatedContextService, can_execute<br/>📄 assistant_lifecycle.py: health_check_loop, start_service, stop_service<br/>📄 memory_manager.py: MemoryManager, execute<br/>📄 soldier_registry.py: SoldierRegistry, execute<br/>📄 github_worker.py: GitHubWorker<br/>📄 jrvs_translator.py: JrvsTranslator, execute<br/>📄 dependency_manager.py: DependencyManager, ensure_capability<br/>📄 meta_reflection.py: MetaReflection, configure<br/>📄 device_capability_service.py: DeviceLocationService, calculate_distance<br/>📄 technical_analysis_service.py: TechnicalAnalysisService, execute<br/>📄 local_bridge.py: LocalBridgeManager, execute<br/>📄 evaluate_risks_service.py: EvaluateRisksService, execute<br/>📄 c2_orchestrator_service.py: KeepAliveProvider, start<br/>📄 scavenger_hunt.py: logger, class, ScavengerHunt<br/>📄 thought_log_types.py: ThoughtType<br/>📄 evolution_orchestrator.py: EvolutionOrchestrator, configure<br/>📄 orchestrator_service.py: OrchestratorService, execute<br/>📄 llm_service.py: LlmService, chat<br/>📄 llm_router.py: LLMRouter, configure<br/>📄 capability_blueprint_service.py: CapabilityBlueprintService, execute<br/>📄 browser_manager.py: PersistentBrowserManager, execute<br/>📄 evolution_gatekeeper.py: EvolutionGatekeeper, configure<br/>📄 task_runner.py: TaskRunner, execute_mission<br/>📄 strategist_service.py: BudgetExceededException, StrategistService<br/>📄 location_service.py: LocationService, execute<br/>📄 status_service.py: StatusService, get_system_report<br/>📄 auto_evolutionV2.py: AutoEvolutionServiceV2, execute<br/>📄 finetune_dataset_collector.py: FineTuneDatasetCollector, configure<br/>📄 device_orchestrator_service.py: SoldierDB, DeviceOrchestratorService<br/>📄 capability_impact_analyzer.py: CapabilityImpactAnalyzer, execute<br/>📄 device_service.py: DeviceService, execute<br/>📄 capability_detectors.py: detect_capability_inventory, detect_capability_classification, detect_existing_capabilities_recognition<br/>📄 llm_capability_prompt_builder.py: extract_keywords, search_files_by_keywords, build_analysis_prompt<br/>📄 serve.py: setup_telegram_webhook<br/>📄 assistant_curiosity.py: maybe_inject_curiosity_question, capture_curiosity_answer<br/>📄 memory_consolidation_service.py: MemoryConsolidationService<br/>📄 curiosity_intake.py: CuriosityIntake, configure<br/>📄 finetune_trigger_service.py: FineTuneTriggerService, configure<br/>📄 extension_manager.py: ExtensionManager, execute<br/>📄 thought_log_renderer.py: ThoughtRenderer, render<br/>📄 assistant_nexus.py: nexus_execute, nexus_can_execute, async_process_command<br/>📄 evolution_sandbox.py: EvolutionSandbox, enabled<br/>📄 curiosity_engine.py: CuriosityEngine<br/>📄 thought_log_service.py: ThoughtLogService, create_thought<br/>📄 local_repair_agent.py: LocalRepairAgent, execute<br/>📄 field_vision.py: FieldVision<br/>📄 assistant_proactivity.py: maybe_get_proactive_suggestion<br/>📄 capability_gap_reporter.py: CapabilityGapReporter, execute<br/>📄 metabolism_core.py: MetabolismCore, execute, ask_jarvis<br/>📄 identify_mission_critical_capabilities.py: identify_mission_critical_capabilities<br/>📄 reconnection_briefing.py: ReconnectionBriefing, execute<br/>📄 assistant_learning.py: check_internal_solution, record_learning_interaction, infer_task_type<br/>📄 prioritizer_service.py: PrioritizerService, execute<br/>📄 device_location_service.py: DeviceLocationService, execute, calculate_distance<br/>📄 model_orchestrator.py: ModelOrchestrator, configure<br/>📄 vocal_orchestration_service.py: VocalOrchestrationService<br/>📄 device_intent_translator.py: DeviceIntentTranslator, can_execute, execute<br/>📄 structured_logger.py: StructuredLogger, execute<br/>📄 agent_task_queue_service.py: TaskQueueUnavailable, AgentTaskQueueService<br/>📄 capability_manager.py: CapabilityManager, execute, implements<br/>📄 main.py: notify_online, run_api, background_bootstrap<br/>📄 thought_log_storage.py: ThoughtLogStorage, db<br/>📄 evolution_loop.py: EvolutionLoopService, configure<br/>📄 human_intervention_service.py: HumanInterventionService, execute<br/>📄 run_workflow.py: RunWorkflow, execute"]
    class app_application_services support
    app_application --> app_application_services
    app_application_services_jarvis_dev_agent["<b>jarvis_dev_agent</b><br/><hr/>📄 agent.py: JarvisDevAgent, configure"]
    class app_application_services_jarvis_dev_agent support
    app_application_services --> app_application_services_jarvis_dev_agent
    app_application_services_crystallization["<b>crystallization</b><br/><hr/>📄 crystallizer_engine.py: CrystallizerEngine, execute"]
    class app_application_services_crystallization support
    app_application_services --> app_application_services_crystallization
    app_application_communication["<b>communication</b><br/><hr/>📄 human_intervention.py: HumanIntervention, execute"]
    class app_application_communication support
    app_application --> app_application_communication
    app_utils["<b>utils</b><br/><hr/>📄 jrvs_codec.py: JrvsDecodeError, encode, decode<br/>📄 document_store.py: DocumentStore, read, write<br/>📄 helpers.py: setup_logging, ensure_directory, sanitize_filename"]
    class app_utils support
    app --> app_utils
    docs["<b>docs</b>"]
    class docs support
    docs_architecture["<b>architecture</b>"]
    class docs_architecture support
    docs --> docs_architecture
    docs_skills-connectors["<b>skills-connectors</b>"]
    class docs_skills-connectors support
    docs --> docs_skills-connectors
    supabase["<b>supabase</b>"]
    class supabase support
    supabase_migrations["<b>migrations</b>"]
    class supabase_migrations support
    supabase --> supabase_migrations
    data["<b>data</b>"]
    class data support
    data_jrvs["<b>jrvs</b>"]
    class data_jrvs support
    data --> data_jrvs
    dags["<b>dags</b><br/><hr/>📄 jarvis_status_dag.py: get_assistant_status, send_notification"]
    class dags support
```
